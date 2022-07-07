import tensorflow as tf
import os
import numpy as np
import pandas as pd
import utils
import quant_GIA
from optparse import OptionParser
from modelzoo import GELU


def gia_occlude_motifs(run_path, data_dir, motif_cluster, background_model, cell_line_name, out_dir='GIA_occlude_results'):
    utils.make_dir(out_dir)  # make output dir
    testset, targets = utils.collect_whole_testset(data_dir=data_dir, coords=True)  # get test set
    C, X, Y = utils.convert_tfr_to_np(testset)  # convert to np arrays for easy filtering
    model, _ = utils.read_model(run_path)  # load model
    run_name = os.path.basename(os.path.abspath(run_path))  # get identifier for the outputs
    gia_occ_dir = utils.make_dir(os.path.join(options.out_dir, run_name))
    base_dir = utils.make_dir(os.path.join(gia_occ_dir, '{}_{}'.format(cell_line_name, args[1])))
    output_dir = utils.make_dir(os.path.join(base_dir, '{}_N{}'.format(background_model, options.n_background)))
    X_set = select_set('all_threshold', C, X, Y)
    gi = GlobalImportance(model, targets)
    if len(motif_cluster) > 1:
        combo_list = [motif_cluster] + [[m] for m in motif_cluster]
    else:
        combo_list = motif_cluster
    for each_element in combo_list:
        print(each_element)
        gi.occlude_all_motif_instances(X_set, each_element, func='mean',
                                      num_sample=n_background)
    df = pd.concat(gi.summary_remove_motifs)
    file_prefix = '{}_in_{}_{}'.format(args[1], cell_line_name, background_model)
    df.to_csv(os.path.join(output_dir, file_prefix+'.csv'), index=None)



def main():
    usage = 'usage: %prog [options] <motifs> <cell_line>'
    parser = OptionParser(usage)

    parser.add_option('-o', dest='out_dir',
        default='seamonster/occlude_GIA_fin',
        help='Output directory [Default: %default]')
    parser.add_option('-n','--n_background', dest='n_background',
        default=1000, type='int',
        help='Sample number for background [Default: %default]')
    parser.add_option('--logits', dest='logits',
        default=False, action='store_true',
        help='take logits [Default: %default]')
    (options, args) = parser.parse_args()
    if len(args) != 4:
        parser.error('Must provide motifs and cell line.')
    else:
        run_path = args[0]
        motif_cluster = args[1].split(',')
        background_model = args[2]
        cell_line_name = args[3]

    print('Processing')
    print(motif_cluster)
    # load and get model layer
    # run_path = 'paper_runs/new_models/32_res/run-20211023_095131-w6okxt01'
    model = tf.keras.models.load_model(run_path, custom_objects={"GELU": GELU})
    utils.make_dir(options.out_dir)
    # load and threshold data
    testset, targets = utils.collect_whole_testset(coords=True)
    C, X, Y = utils.convert_tfr_to_np(testset, 3)
    run_name = [p for p in run_path.split('/') if 'run-' in p][0]
    gia_occ_dir = utils.make_dir(os.path.join(options.out_dir, run_name))
    base_dir = utils.make_dir(os.path.join(gia_occ_dir, '{}_{}'.format(cell_line_name, args[1])))
    output_dir = utils.make_dir(os.path.join(base_dir, '{}_N{}'.format(background_model, options.n_background)))
    # for each element in the cluster of 2 and both together
    # base_dir = util.make_dir(os.path.join(gia_add_dir, '{}_{}'.format(cell_line_name, motif)))
    if background_model == 'dinuc':
        X_set = quant_GIA.select_set('all_threshold', C, X, Y)
    elif background_model == 'none':
        X_set = quant_GIA.select_set('cell_low', C, X, Y, cell_line=np.argwhere(targets==cell_line_name)[0][0])

    gi = quant_GIA.GlobalImportance(model, targets)
    if len(motif_cluster) >1:
        combo_list = [motif_cluster] + [[m] for m in motif_cluster]
    else:
        combo_list = motif_cluster
    for each_element in combo_list:
        print(each_element)
        gi.occlude_all_motif_instances(X_set, each_element, func='mean',
                                      num_sample=options.n_background)
    df = pd.concat(gi.summary_remove_motifs)
    file_prefix = '{}_in_{}_{}'.format(args[1], cell_line_name, background_model)
    df.to_csv(os.path.join(output_dir, file_prefix+'.csv'), index=None)

################################################################################
if __name__ == '__main__':
    main()
