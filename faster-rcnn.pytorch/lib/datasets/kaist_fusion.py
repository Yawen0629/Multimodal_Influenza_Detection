# --------------------------------------------------------
# Fast R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick
# --------------------------------------------------------

import datasets.kaist_fusion
import os
from datasets.imdb import imdb
import xml.dom.minidom as minidom
import numpy as np
import scipy.sparse
import scipy.io as sio
import model.utils.cython_bbox
import cPickle
import subprocess
from model.utils.config import cfg
from .voc_eval import voc_eval


class kaist_thermal(imdb):
    def __init__(self, image_set, devkit_path='/home/dghose/Project/Influenza_Detection/Data/KAIST/Train/set05/V000/lwir/'):
        
        imdb.__init__(self, image_set)  # image_set: train04 or test
        self._image_set = image_set
        self._devkit_path = self._get_default_path()
	#self._devkit_path = '/home/dghose/Project/Influenza_Detection/Data/KAIST/Train/'
        self._devkit_path = '../../data/lwir/'
	self._data_path = os.path.join(self._devkit_path)
        self._classes = ('__background__', # always index 0
                         'person')
        self._class_to_ind = dict(zip(self.classes, xrange(self.num_classes)))
        self._image_ext = '.jpg'
        self._image_index = self._load_image_set_index()
        # Default to roidb handler
        self._roidb_handler = self.selective_search_roidb
	#print('classes')
	#print(self.classes)
        # PASCAL specific config options
        self.config = {'cleanup'     : True,
                       'use_salt'    : True,
                       'use_diff'    : False,
                       'matlab_eval' : False,
                       'rpn_file'    : None,
                       'min_size'    : 2}

        assert os.path.exists(self._devkit_path), \
                'VOCdevkit path does not exist: {}'.format(self._devkit_path)
        assert os.path.exists(self._data_path), \
                'Path does not exist: {}'.format(self._data_path)

    def image_path_at(self, i):
        """
        Return the absolute path to image i in the image sequence.
        """
        return self.image_path_from_index(self._image_index[i])

    def image_path_from_index(self, index):
        """
        Construct an image path from the image's "index" identifier.
        """
        #image_path_1 = os.path.join(self._data_path, self._image_set, 'color',
                                  #index + self._image_ext)
        #image_path_2 = os.path.join(self._data_path, self._image_set, 'thermal',index + self._image_ext)
        #assert (os.path.exists(image_path) ,  'Path does not exist: {}'.format(image_path))
        #image_path=os.path.join('/home/dghose/Project/Influenza_Detection/Data/KAIST/Train/set05/lwir/', index+self._image_ext)
        image_path=os.path.join('../../data/lwir/', index+self._image_ext)

	#print(index,"INDEX!!!")
	return image_path

    def _load_image_set_index(self):
        """
        Load the indexes listed in this dataset's image set file.
        """
        # Example path to image set file:
        # self._devkit_path + /VOCdevkit2007/VOC2007/ImageSets/Main/val.txt
        #image_set_file = os.path.join(self._data_path, self._image_set,
        #                              self._image_set + '.txt')
        
	#image_set_file = '/home/dghose/Project/Influenza_Detection/Code/Multimodal_Influenza_Detection/faster-rcnn.pytorch/imagesetfile.txt'
	image_set_file='../../data/imagesetfile.txt'
	assert os.path.exists(image_set_file), \
                'Path does not exist: {}'.format(image_set_file)
        with open(image_set_file) as f:
            image_index = [x.strip() for x in f.readlines()]
        return image_index


    def _get_default_path(self):
        """
        Return the default path where kaist dataset is expected to be installed.
        """
        return os.path.join(cfg.DATA_DIR, 'kaist')

    def gt_roidb(self):
        """
        Return the database of ground-truth regions of interest.

        This function loads/saves from/to a cache file to speed up future calls.
        """
        cache_file = os.path.join(self.cache_path, self.name + '_gt_roidb.pkl')
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as fid:
                roidb = cPickle.load(fid)
            print '{} gt roidb loaded from {}'.format(self.name, cache_file)
            return roidb

        gt_roidb = [self._load_revised_annotation(index)
                    for index in self.image_index]
        with open(cache_file, 'wb') as fid:
            cPickle.dump(gt_roidb, fid, cPickle.HIGHEST_PROTOCOL)
        print 'wrote gt roidb to {}'.format(cache_file)

        return gt_roidb

    def selective_search_roidb(self):
        """
        Return the database of selective search regions of interest.
        Ground-truth ROIs are also included.

        This function loads/saves from/to a cache file to speed up future calls.
        """
        cache_file = os.path.join(self.cache_path,
                                  self.name + '_selective_search_roidb.pkl')

        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as fid:
                roidb = cPickle.load(fid)
            print '{} ss roidb loaded from {}'.format(self.name, cache_file)
            return roidb

        if self._image_set != 'test-all':
	   # print('in test all---calling load revised annotation and then slective search db')
            gt_roidb = self.gt_roidb()
            ss_roidb = self._load_selective_search_roidb(gt_roidb)
            roidb = imdb.merge_roidbs(gt_roidb, ss_roidb)
        else:
            roidb = self._load_selective_search_roidb(None)
        with open(cache_file, 'wb') as fid:
            cPickle.dump(roidb, fid, cPickle.HIGHEST_PROTOCOL)
        print 'wrote ss roidb to {}'.format(cache_file)

        return roidb

    def _load_selective_search_roidb(self, gt_roidb):
        filename = os.path.abspath(os.path.join(self.cache_path, '..',
                                                'selective_search_data',
                                                self.name + '.mat'))
        assert os.path.exists(filename), \
               'Selective search data not found at: {}'.format(filename)
        raw_data = sio.loadmat(filename)['boxes'].ravel()
	#print('in selective searchDB')
        box_list = []
        for i in xrange(raw_data.shape[0]):
            box_list.append(raw_data[i][:, :] - 1)

        return self.create_roidb_from_box_list(box_list, gt_roidb)

    def selective_search_IJCV_roidb(self):
        """
        Return the database of selective search regions of interest.
        Ground-truth ROIs are also included.

        This function loads/saves from/to a cache file to speed up future calls.
        """
        cache_file = os.path.join(self.cache_path,
                '{:s}_selective_search_IJCV_top_{:d}_roidb.pkl'.
                format(self.name, self.config['top_k']))

        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as fid:
                roidb = cPickle.load(fid)
            print '{} ss roidb loaded from {}'.format(self.name, cache_file)
            return roidb

        gt_roidb = self.gt_roidb()
        ss_roidb = self._load_selective_search_IJCV_roidb(gt_roidb)
        roidb = datasets.imdb.merge_roidbs(gt_roidb, ss_roidb)
        with open(cache_file, 'wb') as fid:
            cPickle.dump(roidb, fid, cPickle.HIGHEST_PROTOCOL)
        print 'wrote ss roidb to {}'.format(cache_file)

        return roidb

    def rpn_roidb(self):
        if self._image_set != 'test-all':
            gt_roidb = self.gt_roidb()
            rpn_roidb = self._load_rpn_roidb(gt_roidb)
            roidb = imdb.merge_roidbs(gt_roidb, rpn_roidb)
        else:
            roidb = self._load_rpn_roidb(None)

        return roidb

    def _load_rpn_roidb(self, gt_roidb):
        filename = self.config['rpn_file']
        print 'loading {}'.format(filename)
        assert os.path.exists(filename), \
               'rpn data not found at: {}'.format(filename)
        with open(filename, 'rb') as f:
            box_list = cPickle.load(f)
        return self.create_roidb_from_box_list(box_list, gt_roidb)

    def _load_selective_search_IJCV_roidb(self, gt_roidb):
        IJCV_path = os.path.abspath(os.path.join(self.cache_path, '..',
                                                 'selective_search_IJCV_data',
                                                 'voc_' + self._year))
        assert os.path.exists(IJCV_path), \
               'Selective search IJCV data not found at: {}'.format(IJCV_path)

        top_k = self.config['top_k']
        box_list = []
        for i in xrange(self.num_images):
            filename = os.path.join(IJCV_path, self.image_index[i] + '.mat')
            raw_data = sio.loadmat(filename)
            box_list.append((raw_data['boxes'][:top_k, :]-1).astype(np.uint16))
        return self.create_roidb_from_box_list(box_list, gt_roidb)

    def _load_revised_annotation(self, index):
        """
        Load image and bounding boxes info from text file in the kaist dataset
        format.
        """

        #filename = os.path.join('/home/dghose/Project/Influenza_Detection/Data/Labels/annotations/set05/V000', index + '.txt')
        # print 'Loading: {}'.format(filename)
	filename=os.path.join('../../data/annotations/set05/V000',index+'.txt')
        with open(filename) as f:
            lines = f.readlines()

        num_objs = len(lines)
	
	
        boxes = np.zeros((num_objs-1, 4), dtype=np.uint16)
        gt_classes = np.zeros((num_objs-1), dtype=np.int32)
        overlaps = np.zeros((num_objs-1, self.num_classes), dtype=np.float32)
        seg_areas = np.zeros((num_objs-1), dtype=np.float32)

        # Load object bounding boxes into a data frame.
        ix = 0
        for obj in lines:
            # Make pixel indexes 0-based
            
            info = obj.split()
            if info[0]== "%":
                continue
            x1 = float(info[1]) 
            y1 = float(info[2])
            x2 = float(info[3])
            y2 = float(info[4])
	    #print('x1,y1,x2,y2')
            #print x1, y1, x2, y2
            #assert(x2>=x1)
            #assert(y2>=y1)
            cls = self._class_to_ind['person']
	    #if cls==0:
		#print('index')
		#print(index)
		#print('ix')
		#print(ix)
	    #if index =='I00383':
		#print('num_obj in image')
		#print(num_objs)	    
		#print('x1 y1 x2 y2')
		#print(x1)
		#print(y1)
		#print(x2)
		#print(y2)
	    #temp1=x1==x2
	    #temp2=y1==y2
	    #if temp1==True:
		#print('xmin==xmax')
		#print(index)
		#print(temp1)
	
 	    #if temp2==True:
		#print('ymin==ymax')
		#print(index)
		#print(temp2)
	    #if x1==-1 or x2==-1 or y1==-1 or y2==-1:
		#print('-1 in annotation')
	    #print(x2)
	    #print(y2)
            boxes[ix, :] = [x1-1, y1-1, x2-1, y2-1]
            gt_classes[ix] = cls
            overlaps[ix, cls] = 1.0
            seg_areas[ix] = (x2 - x1 + 1) * (y2 - y1 + 1)
            ix = ix + 1
        #print(index)
	#if index=='I00383':
		#print(overlaps)

		
        overlaps = scipy.sparse.csr_matrix(overlaps)
	#if index=='I00383':
		#print('after esoteric transformation')
		#print(overlaps)
        return {'boxes' : boxes,
                'gt_classes': gt_classes,
                'gt_overlaps' : overlaps,
                'flipped' : False,
                'seg_areas' : seg_areas}

    def _write_voc_results_file(self, all_boxes):
        use_salt = self.config['use_salt']
        comp_id = 'comp4'
        if use_salt:
            comp_id += '-{}'.format(os.getpid())

        # VOCdevkit/results/VOC2007/Main/comp4-44503_det_test_aeroplane.txt
        path = os.path.join(self._devkit_path, 'results', 'kaist',
                            'Main', comp_id + '_')
        for cls_ind, cls in enumerate(self.classes):
            if cls == '__background__':
                continue
            print 'Writing {} VOC results file'.format(cls)
            #filename = path + 'det_' + self._image_set + '_' + cls + '.txt'
            filename='pedestrian.txt'
            with open(filename, 'wt') as f:
                for im_ind, index in enumerate(self.image_index):
                    dets = all_boxes[cls_ind][im_ind]
                    if dets == []:
                        continue
                    # the VOCdevkit expects 1-based indices
                    for k in xrange(dets.shape[0]):
                        f.write('{:s} {:.3f} {:.1f} {:.1f} {:.1f} {:.1f}\n'.
                                format(index, dets[k, -1],
                                       dets[k, 0] + 1, dets[k, 1] + 1,
                                       dets[k, 2] + 1, dets[k, 3] + 1))
        return comp_id

    def _get_voc_results_file_template(self):
        # VOCdevkit/results/VOC2007/Main/<comp_id>_det_test_aeroplane.txt
        filename = '/home/dghose/Project/Influenza_Detection/Code/Multimodal_Influenza_Detection/faster-rcnn.pytorch/pedestrian.txt'
        path = os.path.join(filename)
        return path



    def _do_python_eval(self, output_dir='output'):
        annopath = os.path.join('/home/dghose/Project/Influenza_Detection/Data/Labels/annotations/set05/V000', '{:s}.txt')
        imagesetfile = '/home/dghose/Project/Influenza_Detection/Code/Multimodal_Influenza_Detection/faster-rcnn.pytorch/imagesetfile.txt'
        cachedir = os.path.join(self._devkit_path, 'annotations_cache')
        aps = []
        # The PASCAL VOC metric changed in 2010
        #use_07_metric = True if int(self._year) < 2010 else False
        #print('VOC07 metric? ' + ('Yes' if use_07_metric else 'No'))
        if not os.path.isdir(output_dir):
            os.mkdir(output_dir)
        for i, cls in enumerate(self._classes):
            if cls == '__background__':
                continue
            filename = '/home/dghose/Project/Influenza_Detection/Code/Multimodal_Influenza_Detection/faster-rcnn.pytorch/pedestrian.txt'
            rec, prec, ap = voc_eval(
                filename, annopath, imagesetfile, cls, cachedir, ovthresh=0.5,
                use_07_metric = False)
            aps += [ap]
            print('AP for {} = {:.4f}'.format(cls, ap))
            with open(os.path.join(output_dir, cls + '_pr.pkl'), 'wb') as f:
                cPickle.dump({'rec': rec, 'prec': prec, 'ap': ap}, f)
        print('Mean AP = {:.4f}'.format(np.mean(aps)))
        print('~~~~~~~~')
        print('Results:')
        for ap in aps:
            print('{:.3f}'.format(ap))
        print('{:.3f}'.format(np.mean(aps)))
        print('~~~~~~~~')
        print('')
        print('--------------------------------------------------------------')
        print('Results computed with the **unofficial** Python eval code.')
        print('Results should be very close to the official MATLAB eval code.')
        print('Recompute with `./tools/reval.py --matlab ...` for your paper.')
        print('-- Thanks, The Management')
        print('--------------------------------------------------------------')





    def _do_matlab_eval(self, comp_id, output_dir='output'):
        rm_results = self.config['cleanup']

        path = os.path.join(os.path.dirname(__file__),
                            'VOCdevkit-matlab-wrapper')
        cmd = 'cd {} && '.format(path)
        cmd += '{:s} -nodisplay -nodesktop '.format(cfg.MATLAB)
        cmd += '-r "dbstop if error; '
        cmd += 'voc_eval(\'{:s}\',\'{:s}\',\'{:s}\',\'{:s}\',{:d}); quit;"' \
               .format(self._devkit_path, comp_id,
                       self._image_set, output_dir, int(rm_results))
        print('Running:\n{}'.format(cmd))
        status = subprocess.call(cmd, shell=True)

    def evaluate_detections(self, all_boxes, output_dir):
        comp_id = self._write_voc_results_file(all_boxes)
        #self._do_matlab_eval(comp_id, output_dir)
        self._do_python_eval(output_dir)
        if self.config['cleanup']:
            for cls in self._classes:
                if cls == '__background__':
                    continue
                filename = self._get_voc_results_file_template().format(cls)
                os.remove(filename)
    

    def competition_mode(self, on):
        if on:
            self.config['use_salt'] = False
            self.config['cleanup'] = False
        else:
            self.config['use_salt'] = True
            self.config['cleanup'] = True

if __name__ == '__main__':
    from datasets.kaist_rgb import kaist_rgb
    d = kaist('train-all02')
    res = d.roidb
    from IPython import embed; embed()
