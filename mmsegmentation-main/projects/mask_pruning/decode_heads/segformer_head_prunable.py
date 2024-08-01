import torch
from mmcv.cnn.bricks.conv_module import ConvModule
from torch import nn

from mmseg.models.decode_heads.decode_head import BaseDecodeHead
from ..utils import mask_class_wrapper
from mmseg.models.utils import resize
from mmseg.registry import MODELS


SegformerHead_Conv2d_pruned = mask_class_wrapper(ConvModule, mode="conv")
@MODELS.register_module()
class SegformerHeadPrunable(BaseDecodeHead):
    """The all mlp Head of segformer.

    This head is the implementation of
    `Segformer <https://arxiv.org/abs/2105.15203>` _.

    Args:
        interpolate_mode: The interpolate mode of MLP head upsample operation.
            Default: 'bilinear'.
    """

    def __init__(self, interpolate_mode='bilinear', k=3, **kwargs):
        super().__init__(input_transform='multiple_select', **kwargs)
        global SegformerHead_Conv2d_pruned
        SegformerHead_Conv2d_pruned = mask_class_wrapper(ConvModule, mode="conv", k=k)

        self.interpolate_mode = interpolate_mode
        num_inputs = len(self.in_channels)

        assert num_inputs == len(self.in_index)

        self.convs = nn.ModuleList()
        for i in range(num_inputs):
            self.convs.append(
                SegformerHead_Conv2d_pruned(
                    in_channels=self.in_channels[i],
                    out_channels=self.channels,
                    kernel_size=1,
                    stride=1,
                    norm_cfg=self.norm_cfg,
                    act_cfg=self.act_cfg))

        self.fusion_conv = SegformerHead_Conv2d_pruned(
            in_channels=self.channels * num_inputs,
            out_channels=self.channels,
            kernel_size=1,
            norm_cfg=self.norm_cfg)

    def forward(self, inputs):
        # Receive 4 stage backbone feature map: 1/4, 1/8, 1/16, 1/32
        inputs = self._transform_inputs(inputs)
        outs = []
        for idx in range(len(inputs)):
            x = inputs[idx]
            conv = self.convs[idx]
            #ident = self.identities[idx]
            #print(conv)
            #print(x)
            outs.append(
                resize(
                    input=conv(x),
                    size=inputs[0].shape[2:],
                    mode=self.interpolate_mode,
                    align_corners=self.align_corners))

        out = self.fusion_conv(torch.cat(outs, dim=1))

        out = self.cls_seg(out)

        return out