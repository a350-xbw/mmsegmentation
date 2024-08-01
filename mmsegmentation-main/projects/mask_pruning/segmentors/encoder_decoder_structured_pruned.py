# Copyright (c) OpenMMLab. All rights reserved.
from typing import Optional

from torch import Tensor

from mmseg.models.segmentors.encoder_decoder import EncoderDecoder
from mmseg.registry import MODELS
from mmseg.utils import (ConfigType, OptConfigType, OptMultiConfig,
                         SampleList)
from ..utils import get_p1_loss


@MODELS.register_module()
class PrunedEncoderDecoder(EncoderDecoder):

    def __init__(self,
                 backbone: ConfigType,
                 decode_head: ConfigType,
                 mask_factor: int = 0.1,
                 neck: OptConfigType = None,
                 auxiliary_head: OptConfigType = None,
                 train_cfg: OptConfigType = None,
                 test_cfg: OptConfigType = None,
                 data_preprocessor: OptConfigType = None,
                 pretrained: Optional[str] = None,
                 init_cfg: OptMultiConfig = None):
        #print("Override CLASSES -----------------------------------------------------")
        self.mask_factor = mask_factor
        super().__init__(backbone=backbone, decode_head=decode_head, neck=neck, auxiliary_head=auxiliary_head,
                         train_cfg=train_cfg, test_cfg=test_cfg, pretrained=pretrained,
                         data_preprocessor=data_preprocessor, init_cfg=init_cfg)

    def loss(self, inputs: Tensor, data_samples: SampleList) -> dict:
        x = self.extract_feat(inputs)

        losses = dict()

        loss_decode = self._decode_head_forward_train(x, data_samples)
        losses.update(loss_decode)

        mask_loss = get_p1_loss(self) * self.mask_factor
        losses["decode.mask_loss"] = mask_loss
        losses["decode.loss_ce"] = losses["decode.loss_ce"]
        #losses.update(add_prefix(get_num_pruned(self), 'decode.pruned'))
        #print(losses)

        if self.with_auxiliary_head:
            loss_aux = self._auxiliary_head_forward_train(x, data_samples)
            losses.update(loss_aux)

        return losses
