from __future__ import absolute_import
# --------------------------------------------------------
# Faster R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick and Sean Bell
# --------------------------------------------------------
# --------------------------------------------------------
# Reorganized and modified by Jianwei Yang and Jiasen Lu
# --------------------------------------------------------

import torch
import torch.nn as nn
import numpy as np
import numpy.random as npr

from model.utils.config import cfg
from .generate_anchors import generate_anchors
from .bbox_transform import clip_boxes, bbox_overlaps_batch, bbox_transform_batch

import pdb

DEBUG = False

try:
    long        # Python 2
except NameError:
    long = int  # Python 3


class _AnchorTargetLayer(nn.Module):
    """
        Assign anchors to ground-truth targets. Produces anchor classification
        labels and bounding-box regression targets.
    """
    def __init__(self, feat_stride, scales, ratios):
        super(_AnchorTargetLayer, self).__init__()

        self._feat_stride = feat_stride
        self._scales = scales
        anchor_scales = scales
        self._anchors = torch.from_numpy(generate_anchors(scales=np.array(anchor_scales), ratios=np.array(ratios))).float()
        self._num_anchors = self._anchors.size(0)

        # allow boxes to sit over the edge by a small amount
        self._allowed_border = 0  # default is 0

    def forward(self, input):
        # Algorithm:
        #
        # for each (H, W) location i
        #   generate 9 anchor boxes centered on cell i
        #   apply predicted bbox deltas at cell i to each of the 9 anchors
        # filter out-of-image anchors
        
        #print("Inside Anchor Target Layer")
        rpn_cls_score = input[0]
        gt_boxes = input[1]
        im_info = input[2]
        num_boxes = input[3]
  	#print('gt_boxes.shape in anchor_target_layer')
	#print(gt_boxes.shape)
	#print('gt_boxes in anchor target layer')
	#print(gt_boxes)
        
	################here we pre-process gt_boxes in such a way that the x1<x2 && y1< y2
	for k in range(gt_boxes.size(1)):
		if(gt_boxes[:,k,0]>gt_boxes[:,k,2]):
			temp=gt_boxes[:,k,0].clone()
			gt_boxes[:,k,0]=gt_boxes[:,k,2]
			#print(temp)
			gt_boxes[:,k,2]=temp	
			#print(gt_boxes[:,k,2])
		if(gt_boxes[:,k,1]>gt_boxes[:,k,3]):
			temp=gt_boxes[:,k,1].clone()
                        gt_boxes[:,k,1]=gt_boxes[:,k,3]
                        gt_boxes[:,k,3]=temp
	#print('gt_box after processinf')
	#print(gt_boxes)
	
	###################################


	# map of shape (..., H, W)
        height, width = rpn_cls_score.size(2), rpn_cls_score.size(3)
        #print("height, width")
        #print(height, width)

        batch_size = gt_boxes.size(0)
	
        feat_height, feat_width = rpn_cls_score.size(2), rpn_cls_score.size(3)
        #print("feature height and width")
        #print(feat_height, feat_width)
        shift_x = np.arange(0, feat_width) * self._feat_stride
        #print("shift_x")
        #print(shift_x)
        shift_y = np.arange(0, feat_height) * self._feat_stride
        #print("shift_y")
        #print(shift_y)
        shift_x, shift_y = np.meshgrid(shift_x, shift_y)
        shifts = torch.from_numpy(np.vstack((shift_x.ravel(), shift_y.ravel(),
                                  shift_x.ravel(), shift_y.ravel())).transpose())
        shifts = shifts.contiguous().type_as(rpn_cls_score).float()
        #print("shifts")
        #print(shifts)

        A = self._num_anchors
        #print("A")
        #print(A)
        K = shifts.size(0)
        #print("K")
        #print(K)

        self._anchors = self._anchors.type_as(gt_boxes) # move to specific gpu.
        all_anchors = self._anchors.view(1, A, 4) + shifts.view(K, 1, 4)
        all_anchors = all_anchors.view(K * A, 4)
        #print("all_anchors")
        #print(all_anchors)
        
        total_anchors = int(K * A)
        #print("total anchors")
        #print(total_anchors)        


        keep = ((all_anchors[:, 0] >= -self._allowed_border) &
                (all_anchors[:, 1] >= -self._allowed_border) &
                (all_anchors[:, 2] < long(im_info[0][1]) + self._allowed_border) &
                (all_anchors[:, 3] < long(im_info[0][0]) + self._allowed_border))
        #print("keep")
        #print(keep)


        inds_inside = torch.nonzero(keep).view(-1)
        #print("inds_inside")
        #print(inds_inside)        


        # keep only inside anchors
        anchors = all_anchors[inds_inside, :]
        #print(anchors.shape)
        #print((anchors))
	#print('gt_box in anchor target')
	#print(gt_boxes)
        # label: 1 is positive, 0 is negative, -1 is dont care
        labels = gt_boxes.new(batch_size, inds_inside.size(0)).fill_(-1)
        #print('labels')
	#print(labels)
	
        bbox_inside_weights = gt_boxes.new(batch_size, inds_inside.size(0)).zero_()
        #print("bbox_inside_weights")
        #print(bbox_inside_weights)
        bbox_outside_weights = gt_boxes.new(batch_size, inds_inside.size(0)).zero_()
        #print("bbox_outside_weights")
        #print(bbox_outside_weights)        


        overlaps = bbox_overlaps_batch(anchors, gt_boxes)
        #print(overlaps.shape)
	#print('overlaps')
	#print(overlaps)
	'''
#############
	#if len(overlaps.size())==2:
#
 		overlaps=overlaps.unsqueeze(-1)
		print(overlaps.size())
##############
	'''	
        max_overlaps, argmax_overlaps = torch.max(overlaps, 2)
        #print("max_overlaps, argmax_overlaps")
        #print(max_overlaps, argmax_overlaps)
        gt_max_overlaps, _ = torch.max(overlaps, 1)
        #print("gt_max_overlaps")
        #print(gt_max_overlaps)        
	#print('ye nahi')
        if not cfg.TRAIN.RPN_CLOBBER_POSITIVES:
            labels[max_overlaps < cfg.TRAIN.RPN_NEGATIVE_OVERLAP] = 0
            #print("inside if not")
            
        gt_max_overlaps[gt_max_overlaps==0] = 1e-5
        keep = torch.sum(overlaps.eq(gt_max_overlaps.view(batch_size,1,-1).expand_as(overlaps)), 2)
        #print("keep - 1")
        #print(keep)
        if torch.sum(keep) > 0:
            labels[keep>0] = 1

        # fg label: above threshold IOU
        labels[max_overlaps >= cfg.TRAIN.RPN_POSITIVE_OVERLAP] = 1

        if cfg.TRAIN.RPN_CLOBBER_POSITIVES:
            labels[max_overlaps < cfg.TRAIN.RPN_NEGATIVE_OVERLAP] = 0

        num_fg = int(cfg.TRAIN.RPN_FG_FRACTION * cfg.TRAIN.RPN_BATCHSIZE)
        #print("num fg")
        #print(num_fg)
        sum_fg = torch.sum((labels == 1).int(), 1)
        #print("sum_fg")
        #print(sum_fg)
        sum_bg = torch.sum((labels == 0).int(), 1)
        #print("sum_bg")
        #print(sum_bg)
        for i in range(batch_size):
            # subsample positive labels if we have too many
            if sum_fg[i] > num_fg:
                #print("inside if")
                fg_inds = torch.nonzero(labels[i] == 1).view(-1)
                #print("fg_inds")
                #print(fg_inds)
                # torch.randperm seems has a bug on multi-gpu setting that cause the segfault.
                # See https://github.com/pytorch/pytorch/issues/1868 for more details.
                # use numpy instead.
                #rand_num = torch.randperm(fg_inds.size(0)).type_as(gt_boxes).long()
                rand_num = torch.from_numpy(np.random.permutation(fg_inds.size(0))).type_as(gt_boxes).long()
                disable_inds = fg_inds[rand_num[:fg_inds.size(0)-num_fg]]
                labels[i][disable_inds] = -1

#           num_bg = cfg.TRAIN.RPN_BATCHSIZE - sum_fg[i]
            num_bg = cfg.TRAIN.RPN_BATCHSIZE - torch.sum((labels == 1).int(), 1)[i]
            #print("num_bg")
            #print(num_bg)
            # subsample negative labels if we have too many
            if sum_bg[i] > num_bg:
                #print("inside if")
                bg_inds = torch.nonzero(labels[i] == 0).view(-1)
                #print("bg_inds")
                #print(bg_inds)
                #rand_num = torch.randperm(bg_inds.size(0)).type_as(gt_boxes).long()

                rand_num = torch.from_numpy(np.random.permutation(bg_inds.size(0))).type_as(gt_boxes).long()
                disable_inds = bg_inds[rand_num[:bg_inds.size(0)-num_bg]]
                labels[i][disable_inds] = -1

        offset = torch.arange(0, batch_size)*gt_boxes.size(1)
        #print("offset")
        #print(offset)
        argmax_overlaps = argmax_overlaps + offset.view(batch_size, 1).type_as(argmax_overlaps)
        #print("argmax_overlaps")
        #print(argmax_overlaps)
	#print('gt_boxes.view(-1,5)[argmax_overlaps.view(-1), :].view(batch_size, -1, 5')
	#print(gt_boxes.view(-1,5)[argmax_overlaps.view(-1), :].view(batch_size, -1, 5))
        bbox_targets = _compute_targets_batch(anchors, gt_boxes.view(-1,5)[argmax_overlaps.view(-1), :].view(batch_size, -1, 5))
        #print('back from bbox_transform#####:::#####')
        #print("bbox_targets")
        #print(bbox_targets)
        # use a single value instead of 4 values for easy index.
        bbox_inside_weights[labels==1] = cfg.TRAIN.RPN_BBOX_INSIDE_WEIGHTS[0]
        #print("bbox_inside_weights")
        #print(bbox_inside_weights)
        if cfg.TRAIN.RPN_POSITIVE_WEIGHT < 0:
            num_examples = torch.sum(labels[i] >= 0)
            positive_weights = 1.0 / num_examples.item()
            negative_weights = 1.0 / num_examples.item()
        else:
            assert ((cfg.TRAIN.RPN_POSITIVE_WEIGHT > 0) &
                    (cfg.TRAIN.RPN_POSITIVE_WEIGHT < 1))

        bbox_outside_weights[labels == 1] = positive_weights
        bbox_outside_weights[labels == 0] = negative_weights

        labels = _unmap(labels, total_anchors, inds_inside, batch_size, fill=-1)
        bbox_targets = _unmap(bbox_targets, total_anchors, inds_inside, batch_size, fill=0)
        bbox_inside_weights = _unmap(bbox_inside_weights, total_anchors, inds_inside, batch_size, fill=0)
        bbox_outside_weights = _unmap(bbox_outside_weights, total_anchors, inds_inside, batch_size, fill=0)

        outputs = []

        labels = labels.view(batch_size, height, width, A).permute(0,3,1,2).contiguous()
        labels = labels.view(batch_size, 1, A * height, width)
        outputs.append(labels)

        bbox_targets = bbox_targets.view(batch_size, height, width, A*4).permute(0,3,1,2).contiguous()
        outputs.append(bbox_targets)

        anchors_count = bbox_inside_weights.size(1)
        bbox_inside_weights = bbox_inside_weights.view(batch_size,anchors_count,1).expand(batch_size, anchors_count, 4)

        bbox_inside_weights = bbox_inside_weights.contiguous().view(batch_size, height, width, 4*A)\
                            .permute(0,3,1,2).contiguous()

        outputs.append(bbox_inside_weights)

        bbox_outside_weights = bbox_outside_weights.view(batch_size,anchors_count,1).expand(batch_size, anchors_count, 4)
        bbox_outside_weights = bbox_outside_weights.contiguous().view(batch_size, height, width, 4*A)\
                            .permute(0,3,1,2).contiguous()
        outputs.append(bbox_outside_weights)

        return outputs

    def backward(self, top, propagate_down, bottom):
        """This layer does not propagate gradients."""
        pass

    def reshape(self, bottom, top):
        """Reshaping happens during the call to forward."""
        pass

def _unmap(data, count, inds, batch_size, fill=0):
    """ Unmap a subset of item (data) back to the original set of items (of
    size count) """

    if data.dim() == 2:
        ret = torch.Tensor(batch_size, count).fill_(fill).type_as(data)
        ret[:, inds] = data
    else:
        ret = torch.Tensor(batch_size, count, data.size(2)).fill_(fill).type_as(data)
        ret[:, inds,:] = data
    return ret


def _compute_targets_batch(ex_rois, gt_rois):
    """Compute bounding-box regression targets for an image."""

    #print('entering bbox transform batch')
    ret_val=bbox_transform_batch(ex_rois, gt_rois[:, :, :4])
    #print('ret_val in compute_targets_batch')
    #print(ret_val)
    return ret_val
    
    
