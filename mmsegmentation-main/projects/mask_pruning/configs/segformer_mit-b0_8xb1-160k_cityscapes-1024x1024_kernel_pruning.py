_base_ = [
    '../../../configs/_base_/models/segformer_mit-b0.py',
    '../../../configs/_base_/datasets/cityscapes_1024x1024.py',
    '../../../configs/_base_/default_runtime.py', '../../../configs/_base_/schedules/schedule_160k.py'
]
crop_size = (1024, 1024)
data_preprocessor = dict(size=crop_size)
checkpoint = './pretrained_weight/segformer/mit_b0_prunable_20220624-7e0fe6dd.pth'  # noqa
model = dict(
    type="PrunedEncoderDecoder",
    mask_factor=0.1,
    data_preprocessor=data_preprocessor,
    backbone=dict(type='MixVisionTransformerPrunable', embed_dims=32, init_cfg=dict(type='Pretrained', checkpoint=checkpoint)),
    decode_head=dict(type="SegformerHeadKernelPruning"),
    test_cfg=dict(mode='slide', crop_size=(1024, 1024), stride=(768, 768)))

optim_wrapper = dict(
    _delete_=True,
    type='OptimWrapper',
    optimizer=dict(
        type='AdamW', lr=0.00006, betas=(0.9, 0.999), weight_decay=0.01),
    accumulative_counts=1,
    paramwise_cfg=dict(
        custom_keys={
            'pos_block': dict(decay_mult=0.),
            'norm': dict(decay_mult=0.),
            'head': dict(lr_mult=10.),
            'p1': dict(lr_mult=10.)
        }))

param_scheduler = [
    dict(
        type='LinearLR', start_factor=1e-6, by_epoch=False, begin=0, end=1500),
    dict(
        type='PolyLR',
        eta_min=0.0,
        power=1.0,
        begin=1500,
        end=160000,
        by_epoch=False,
    )
]

train_dataloader = dict(batch_size=1, num_workers=4)
val_dataloader = dict(batch_size=1, num_workers=4)
test_dataloader = val_dataloader
train_cfg = dict(
    type='IterBasedTrainLoop', max_iters=160000, val_interval=8000)

custom_hooks = [
    dict(type='MaskPruningHook', do_explicit_pruning=False, prune_at_start=False, logging_interval=5000, pruning_interval=5000, debug=True),
]

