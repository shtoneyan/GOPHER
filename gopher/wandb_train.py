#!/usr/bin/env python
import custom_fit
import h5py
import json
import modelzoo
import os
import sys
import tensorflow as tf
import utils
import wandb
import yaml
import sys
from wandb.keras import WandbCallback


def fit_robust(model_name_str, loss_type_str, window_size, bin_size, data_dir,
               output_dir, config={}):
    """

    :param model_name_str: func name defined in the modelzoo.py
    :param loss_type_str: loss func name defines in losses.py
    :param window_size: input length for the model
    :param bin_size: bin resolution
    :param data_dir: dataset path
    :param output_dir: output where to save the model
    :param config: set of parameters for defining a run
    :return: training metrics history
    """

    default_config = {'num_epochs': 30, 'batch_size': 64, 'shuffle': True,
                      'metrics': ['mse', 'pearsonr', 'poisson'], 'es_start_epoch': 1,
                      'l_rate': 0.001, 'es_patience': 6, 'es_metric': 'loss',
                      'es_criterion': 'min', 'lr_decay': 0.3, 'lr_patience': 10,
                      'lr_metric': 'loss', 'lr_criterion': 'min', 'verbose': True,
                      'log_wandb': True, 'rev_comp': True, 'crop': True,
                      'record_test': False, 'alpha': False, 'loss_params': [],
                      'sigma': 20}

    for key in default_config.keys():
        if key in config.keys():
            default_config[key] = config[key]

    if default_config['log_wandb'] == False:
        wandb_style_config = {}
        for k, v in default_config.items():
            wandb_style_config[k] = {'value': v}
        for k, v in {'model_fn': model_name_str, 'loss_fn': loss_type_str, 'input_size': window_size,
                     'bin_size': bin_size, 'data_dir': data_dir}.items():
            wandb_style_config[k] = {'value': v}
        output_dir = utils.make_dir(os.path.join(output_dir, 'files'))  # overwrite so that model is also saved there
        with open(os.path.join(output_dir, 'config.yaml'), 'w') as file:

            documents = yaml.dump(wandb_style_config, file)

    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)

    optimizer = tf.keras.optimizers.Adam(learning_rate=default_config['l_rate'])
    model = eval('modelzoo.' + model_name_str)  # get model function from model zoo
    output_len = window_size // bin_size

    loss = eval('losses.' + loss_type_str)(loss_params=default_config['loss_params'])

    trainset = utils.make_dataset(data_dir, 'train', utils.load_stats(data_dir),
                                  batch_size=default_config['batch_size'])
    validset = utils.make_dataset(data_dir, 'valid', utils.load_stats(data_dir), batch_size=default_config['batch_size'])

    json_path = os.path.join(data_dir, 'statistics.json')
    with open(json_path) as json_file:
        params = json.load(json_file)
    print(params['num_targets'])
    if loss_type_str == 'poisson' and model_name_str == 'bpnet':
        model = model((window_size, 4), (output_len, params['num_targets']), softplus=True, wandb_config=config)
    else:
        model = model((window_size, 4), (output_len, params['num_targets']), wandb_config=config)

    if not model:
        raise BaseException('Fatal filter N combination!')

    print(model.summary())
    train_seq_len = params['train_seqs']
    if model_name_str == 'ori_bpnet':
        # create trainer class
        trainer = custom_fit.RobustTrainer(model, loss, optimizer, window_size, bin_size, params['num_targets'],
                                           default_config['metrics'],
                                           ori_bpnet_flag=True, rev_comp=default_config['rev_comp'],
                                           crop=default_config['crop'],
                                           sigma=default_config['sigma'])
    else:
        trainer = custom_fit.RobustTrainer(model, loss, optimizer, window_size, bin_size, params['num_targets'],
                                           default_config['metrics'],
                                           ori_bpnet_flag=False, rev_comp=default_config['rev_comp'],
                                           crop=default_config['crop'],
                                           sigma=default_config['sigma'])

    # set up learning rate decay
    trainer.set_lr_decay(decay_rate=default_config['lr_decay'], patience=default_config['lr_patience'],
                         metric=default_config['lr_metric'], criterion=default_config['lr_criterion'])
    trainer.set_early_stopping(patience=default_config['es_patience'], metric=default_config['es_metric'],
                               criterion=default_config['es_criterion'])

    # train model
    for epoch in range(default_config['num_epochs']):
        sys.stdout.write("\rEpoch %d \n" % (epoch + 1))

        # Robust train with crop and bin
        trainer.robust_train_epoch(trainset, num_step=train_seq_len // default_config['batch_size'] + 1,
                                   batch_size=default_config['batch_size'])

        # validation performance
        trainer.robust_evaluate('val', validset,
                                batch_size=default_config['batch_size'], verbose=default_config['verbose'])

        # check learning rate decay
        trainer.check_lr_decay('loss')

        # check early stopping
        if epoch >= default_config['es_start_epoch']:

            if trainer.check_early_stopping('val'):
                print("Patience ran out... Early stopping.")
                break
        if default_config['log_wandb']:
            # Logging with W&B
            current_hist = trainer.get_current_metrics('train')
            wandb.log(trainer.get_current_metrics('val', current_hist))

    # compile history
    history = trainer.get_metrics('train')
    history = trainer.get_metrics('val', history)
    model.save(os.path.join(output_dir, "best_model.h5"))
    return history

def train_binary(model_name_str,data_dir,window_size,output_dir,config = {}):
    default_config = {'num_epochs': 100, 'batch_size': 64,
                      'es_patience': 10, 'verbose' : True,'l_rate':0.001,
                      'lr_patience': 3, 'lr_decay': 0.2,
                      'loss_fn': 'BinaryCrossentrophy','log_wandb':True}

    for key in default_config.keys():
        if key in config.keys():
            default_config[key] = config[key]

    f = h5py.File(data_dir,'r')
    train_x = f['x_train'][()]
    train_y = f['y_train'][()]

    valid_x = f['x_valid'][()]
    valid_y = f['y_valid'][()]
    f.close()

    model = eval('modelzoo.' + model_name_str)((window_size,4),len(valid_y[0]),wandb_config=config)

    if default_config['log_wandb'] == False:
        wandb_style_config = {}
        for k, v in default_config.items():
            wandb_style_config[k] = {'value': v}
        for k, v in {'model_fn': model_name_str, 'input_size': window_size,
                     'data_dir': data_dir}.items():
            wandb_style_config[k] = {'value': v}
        output_dir = utils.make_dir(os.path.join(output_dir, 'files'))  # overwrite so that model is also saved there
        with open(os.path.join(output_dir, 'config.yaml'), 'w') as file:
            documents = yaml.dump(wandb_style_config, file)
        history = model.fit(train_x,train_y,
                        epochs=default_config['num_epochs'],
                        batch_size = default_config['batch_size'],
                        callbacks = [modelzoo.early_stopping(patience = default_config['es_patience'],
                                                        verbose = int(default_config['verbose'])),
                                     modelzoo.model_checkpoint(output_dir+'/best_model.h5'),
                                     modelzoo.reduce_lr(patience = default_config['lr_patience'],
                                                factor = default_config['lr_decay'])
                                     ],
                        validation_data = (valid_x,valid_y),
                        )
    else:
        history = model.fit(train_x,train_y,
                        epochs=default_config['num_epochs'],
                        batch_size = default_config['batch_size'],
                        callbacks = [modelzoo.early_stopping(patience = default_config['es_patience'],
                                                        verbose = int(default_config['verbose'])),
                                     modelzoo.model_checkpoint(output_dir+'/best_model.h5'),
                                     modelzoo.reduce_lr(patience = default_config['lr_patience'],
                                                factor = default_config['lr_decay']),
                                     WandbCallback()
                                     ],
                        validation_data = (valid_x,valid_y),
                        )
    return history


def train_config(config=None):
    with wandb.init(config=config) as run:
        config = wandb.config
        if config.task_type == 'binary':
            history = train_binary(config.model_fn,config.data_dir,
                                    config.window_size,wandb.run.dir,config=config)
        else:
            history = fit_robust(config.model_fn, config.loss_fn,
                                config.window_size, config.bin_size, config.data_dir,
                                output_dir=wandb.run.dir, config=config)


def main():
    exp_id = sys.argv[1]
    exp_n = sys.argv[2]
    if 'sweeps' in exp_id:
        exp_id = '/'.join(exp_id.split('/sweeps/'))
    else:
        raise BaseException('Sweep ID invalid!')
    sweep_id = exp_id
    wandb.login()
    wandb.agent(sweep_id, train_config, count=exp_n)


# __main__
################################################################################
if __name__ == '__main__':
    main()
