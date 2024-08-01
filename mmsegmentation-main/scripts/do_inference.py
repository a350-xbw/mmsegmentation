import os
import pathlib
import os.path as osp
import pandas as pd
import torch.cuda

from mmengine.config import Config
from mmengine.runner import Runner
from tools.analysis_tools.benchmark import benchmark
from tools.analysis_tools.get_flops import get_model_complexity_info
from mmengine.analysis.print_helper import _format_size

from mmseg.utils import register_all_modules
from scripts.get_checkpoint import get_checkpoint
from argparse import ArgumentParser
from mmcv.transforms import CenterCrop
from get_flops_segformer import get_additional_segformer_flops
import projects

from zeus.monitor import ZeusMonitor
from mmengine.config import Config, DictAction


def main():
    parser = ArgumentParser()
    parser.add_argument('--config', help='path to the configuration yaml file as in tables/from_mmseg/all.csv')
    parser.add_argument(
        '--input-shape',
        nargs='+',
        type=int,
        default=(3, 512, 512),
        help='the shape of the input')
    parser.add_argument(
        '--cfg-options',
        nargs='+',
        action=DictAction,
        help='override some settings in the used config, the key-value pair '
             'in xxx=yyy format will be merged into config file. If the value to '
             'be overwritten is a list, it should be like key="[a,b]" or key=a,b '
             'It also allows nested list/tuple values, e.g. key="[(a,b),(c,d)]" '
             'Note that the quotation marks are necessary and that no white space '
             'is allowed.')
    parser.add_argument('--no_ckpt', action='store_true', help='do not initialize weights from checkpoint')
    parser.add_argument('--prefix', default=None, help='prefix to indicate the hardware used')
    parser.add_argument('--checkpoint-path', default=None, help='path to the checkpoint file')
    args = parser.parse_args()
    do_inference(args.config, not args.no_ckpt, input_shape=tuple(args.input_shape), prefix=args.prefix, checkpoint_path=args.checkpoint_path, cfg_options=args.cfg_options)


def do_inference(config_path, use_ckpt=True, input_shape=(3, 512, 512), prefix=None, checkpoint_path=None, cfg_options=None):
    debug = (not torch.cuda.is_available()) or (os.environ.get('MACHINE', default='cluster') != 'cluster')
    print(f'{debug=}')
    repeat_times, n_images_benchmark, n_warmup, n_images_total = (6, 4, 2, 5) if debug else (3, 250, 50, None)
    if checkpoint_path is None:
        ckpt = get_checkpoint(config_path) if use_ckpt else None
    else:
        ckpt = checkpoint_path
    register_all_modules()
    cfg = Config.fromfile(config_path)
    if cfg_options is not None:
        cfg.merge_from_dict(cfg_options)
    if n_images_total:  # if not specified use entire dataset
        cfg['test_dataloader']['dataset']['indices'] = n_images_total
    """cfg['visualizer']['vis_backends'] = [
        dict(
        type='WandbVisBackend',
        init_kwargs=dict(
            entity='js0',
            project='mmseg_inference',
            reinit=True,
            name=pathlib.Path(config_path).stem,
            notes=os.environ.get('SLURM_JOB_ID', ''),
                         ),
        watch_kwargs=dict(log_graph=True, log_freq=1),
    )]"""
    cfg.work_dir = 'inference_results'
    save_dir = f'tables/reproduced'
    if prefix:
        cfg.work_dir += f'_{prefix}'
        save_dir += f'_{prefix}'
    cfg.load_from = ckpt
    cfg.resume = False  # we dont want to continue training, just load the weights
    runner = Runner.from_cfg(cfg)
    runner.model.eval()
    runner.call_hook('before_test')
    def input_ctor(*args, **kwargs):
        batch = next(iter(runner.test_dataloader))  # train_dataloader uses crops with correct size
        batch = runner.model.data_preprocessor(batch)
        metainfo = batch['data_samples'][0].metainfo
        metainfo['batch_input_shape'] = metainfo['img_shape']
        batch['data_samples'][0].set_metainfo(metainfo)
        method = config_path.split('/')[-2]
        if method not in 'maskformer mask2former'.split():
            batch['data_samples'] = None
        return batch

    #runner.test_dataloader.dataset.pipeline.transforms.insert(2, CenterCrop(crop_size=(512, 512)))

    #flops, params = get_model_complexity_info(runner.model, input_shape, as_strings=False,
    #                                          input_constructor=input_ctor # needed?
     #                                         )

    outputs = get_model_complexity_info(
        runner.model, input_shape,
        show_table=True,
        show_arch=False)

    flops = _format_size(outputs['flops'])
    params = _format_size(outputs['params'])

    """if 'segformer' in config_path:
        flops = float(flops[:-1])
        atn_flops = sum(get_additional_segformer_flops(runner.model, input_shape))
        atn_flops /= 1000000000.0
        flops += atn_flops
        flops = str(round(flops, 3)) + 'G'"""

    runner = Runner.from_cfg(cfg)
    benchmark_metrics = benchmark(config_path, repeat_times=repeat_times, n_images=n_images_benchmark, n_warmup=n_warmup)
    monitor = ZeusMonitor(gpu_indices=[0])
    monitor.begin_window("heavy computation")
    metrics = runner.test()
    measurement = monitor.end_window("heavy computation")
    print(f"Energy: {measurement.total_energy} J")
    print(f"Time  : {measurement.time} s")
    print(f"FLOPs: {flops}")

    results = dict(
        flops=flops,
        params=params,
        fps=benchmark_metrics['average_fps'],
        fps_var=benchmark_metrics['fps_variance'],
        mIoU=metrics['mIoU'],
        energy=measurement.total_energy,
        energy_time=measurement.time,
    )
    if debug:
        save_dir += '_debug'
    os.makedirs(save_dir, exist_ok=True)
    df = pd.DataFrame([results])
    filename = f'{save_dir}/{osp.basename(config_path)}.csv'
    df.to_csv(filename, index=False)


if __name__ == '__main__':
    main()

