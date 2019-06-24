import os
import sys

sys.path.append('../../')
import time
import numpy
from six.moves import xrange  # pylint: disable=redefined-builtin
import tensorflow as tf
import input_data
import math
import numpy as np
from i3d import InceptionI3d
from utils import *
from tensorflow.python import pywrap_tensorflow

# Basic model parameters as external flags.
flags = tf.app.flags
gpu_num = 1
flags.DEFINE_float('learning_rate', 0.0001, 'Initial learning rate.')
flags.DEFINE_integer('max_steps', 30000, 'Number of steps to run trainer.')
flags.DEFINE_integer('batch_size', 4, 'Batch size.')
flags.DEFINE_integer('num_frame_per_clib', 32, 'Nummber of frames per clib')
flags.DEFINE_integer('crop_size', 224, 'Crop_size')
flags.DEFINE_integer('rgb_channels', 3, 'RGB_channels for input')
flags.DEFINE_integer('flow_channels', 2, 'FLOW_channels for input')
flags.DEFINE_integer('classics', 101, 'The num of class')
FLAGS = flags.FLAGS
model_save_dir = './models/pre_scratch_30000_4_32_0.0001_decay'

os.environ["CUDA_VISIBLE_DEVICES"] = "1"


def run_training():
    # Get the sets of images and labels for training, validation, and
    # Tell TensorFlow that the model will be built into the default Graph.

    # Create model directory
    if not os.path.exists(model_save_dir):
        os.makedirs(model_save_dir)
    rgb_pre_model_save_dir = "/home/ly/workspace/i3d/checkpoints/rgb_scratch"
    flow_pre_model_save_dir = "/home/ly/workspace/i3d/checkpoints/flow_scratch"

    with tf.Graph().as_default():
        global_step = tf.get_variable(
            'global_step',
            [],
            initializer=tf.constant_initializer(0),
            trainable=False
        )
        rgb_images_placeholder, flow_images_placeholder, labels_placeholder, is_training = placeholder_inputs(
            FLAGS.batch_size * gpu_num,
            FLAGS.num_frame_per_clib,
            FLAGS.crop_size,
            FLAGS.rgb_channels,
            FLAGS.flow_channels
        )

        learning_rate = tf.train.exponential_decay(FLAGS.learning_rate, global_step, decay_steps=10000, decay_rate=0.1,
                                                   staircase=True)
        opt_rgb = tf.train.AdamOptimizer(learning_rate)
        opt_flow = tf.train.AdamOptimizer(learning_rate)
        # opt_stable = tf.train.MomentumOptimizer(learning_rate, 0.9)
        with tf.variable_scope('RGB'):
            rgb_logit, _ = InceptionI3d(
                num_classes=FLAGS.classics,
                spatial_squeeze=True,
                final_endpoint='Logits'
            )(rgb_images_placeholder, is_training)
        with tf.variable_scope('Flow'):
            flow_logit, _ = InceptionI3d(
                num_classes=FLAGS.classics,
                spatial_squeeze=True,
                final_endpoint='Logits'
            )(flow_images_placeholder, is_training)
        rgb_loss = tower_loss(
            rgb_logit,
            labels_placeholder
        )
        flow_loss = tower_loss(
            flow_logit,
            labels_placeholder
        )
        predict = tf.add(tf.nn.softmax(rgb_logit), tf.nn.softmax(flow_logit))
        accuracy = tower_acc(predict, labels_placeholder)
        rgb_variable_list = {}
        flow_variable_list = {}
        for variable in tf.global_variables():
            if variable.name.split('/')[0] == 'RGB':
                rgb_variable_list[variable.name] = variable

        for variable in tf.global_variables():
            if variable.name.split('/')[0] == 'Flow':
                flow_variable_list[variable.name] = variable
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(update_ops):
            rgb_grads = opt_rgb.compute_gradients(rgb_loss, var_list=rgb_variable_list)
            flow_grads = opt_flow.compute_gradients(flow_loss, var_list=flow_variable_list)
            apply_gradient_rgb = opt_rgb.apply_gradients(rgb_grads, global_step=global_step)
            apply_gradient_flow = opt_flow.apply_gradients(flow_grads, global_step=global_step)
            train_op = tf.group(apply_gradient_rgb, apply_gradient_flow)
            null_op = tf.no_op()

        # Create a saver for loading trained checkpoints.
        rgb_variable_map = {}
        flow_variable_map = {}
        for variable in tf.global_variables():
            if variable.name.split('/')[0] == 'RGB' and 'Adam' not in variable.name.split('/')[-1] and \
                    variable.name.split('/')[2] != 'Logits':
                # rgb_variable_map[variable.name.replace(':0', '')[len('RGB/inception_i3d/'):]] = variable
                rgb_variable_map[variable.name.replace(':0', '')] = variable
        rgb_saver = tf.train.Saver(var_list=rgb_variable_map, reshape=True)

        for variable in tf.global_variables():
            if variable.name.split('/')[0] == 'Flow' and 'Adam' not in variable.name.split('/')[-1] and \
                    variable.name.split('/')[2] != 'Logits':
                flow_variable_map[variable.name.replace(':0', '')] = variable
        flow_saver = tf.train.Saver(var_list=flow_variable_map, reshape=True)

        # Create a saver for writing training checkpoints.
        saver = tf.train.Saver()
        init = tf.global_variables_initializer()

        # Create a session for running Ops on the Graph.
        sess = tf.Session(
            config=tf.ConfigProto(allow_soft_placement=True)
        )
        sess.run(init)
        # Create summary writter
        tf.summary.scalar('accuracy', accuracy)
        tf.summary.scalar('rgb_loss', rgb_loss)
        tf.summary.scalar('flow_loss', flow_loss)
        tf.summary.scalar('learning_rate', learning_rate)
        merged = tf.summary.merge_all()
    # load pre_train models
    ckpt = tf.train.get_checkpoint_state(rgb_pre_model_save_dir)
    if ckpt and ckpt.model_checkpoint_path:
        print("loading checkpoint %s,waiting......" % ckpt.model_checkpoint_path)
        rgb_saver.restore(sess, ckpt.model_checkpoint_path)
        print("load complete!")
    ckpt = tf.train.get_checkpoint_state(flow_pre_model_save_dir)
    if ckpt and ckpt.model_checkpoint_path:
        print("loading checkpoint %s,waiting......" % ckpt.model_checkpoint_path)
        flow_saver.restore(sess, ckpt.model_checkpoint_path)
        print("load complete!")

    train_writer = tf.summary.FileWriter('./visual_logs/train_pre_imagenet_30000_4_64_0.0001_decay', sess.graph)
    test_writer = tf.summary.FileWriter('./visual_logs/test_pre_imagenet_30000_4_64_0.0001_decay', sess.graph)
    for step in xrange(FLAGS.max_steps):
        start_time = time.time()
        rgb_train_images, flow_train_images, train_labels, _, _, _ = input_data.read_clip_and_label(
            filename='../../list/ucf_list/train_flow.list',
            batch_size=FLAGS.batch_size * gpu_num,
            num_frames_per_clip=FLAGS.num_frame_per_clib,
            crop_size=FLAGS.crop_size,
            shuffle=True,
            add_flow=True
        )
        sess.run(train_op, feed_dict={
            rgb_images_placeholder: rgb_train_images,
            flow_images_placeholder: flow_train_images,
            labels_placeholder: train_labels,
            is_training: True
        })
        duration = time.time() - start_time
        print('Step %d: %.3f sec' % (step, duration))

        # Save a checkpoint and evaluate the model periodically.
        if step % 10 == 0 or (step + 1) == FLAGS.max_steps:
            print('Training Data Eval:')
            summary, acc, loss_rgb, loss_flow = sess.run(
                [merged, accuracy, rgb_loss, flow_loss],
                feed_dict={rgb_images_placeholder: rgb_train_images,
                           flow_images_placeholder: flow_train_images,
                           labels_placeholder: train_labels,
                           is_training: False
                           })
            print("accuracy: " + "{:.5f}".format(acc))
            print("rgb_loss: " + "{:.5f}".format(loss_rgb))
            print("flow_loss: " + "{:.5f}".format(loss_flow))
            train_writer.add_summary(summary, step)
            print('Validation Data Eval:')
            rgb_val_images, flow_val_images, val_labels, _, _, _ = input_data.read_clip_and_label(
                filename='../../list/ucf_list/test_flow.list',
                batch_size=FLAGS.batch_size * gpu_num,
                num_frames_per_clip=FLAGS.num_frame_per_clib,
                crop_size=FLAGS.crop_size,
                shuffle=True
            )
            summary, acc = sess.run(
                [merged, accuracy],
                feed_dict={
                    rgb_images_placeholder: rgb_val_images,
                    flow_images_placeholder: flow_val_images,
                    labels_placeholder: val_labels,
                    is_training: False
                })
            print("accuracy: " + "{:.5f}".format(acc))
            test_writer.add_summary(summary, step)
        if (step + 1) % 3000 == 0 or (step + 1) == FLAGS.max_steps:
            saver.save(sess, os.path.join(model_save_dir, 'i3d_ucf_model'), global_step=step)
    print("done")


def main(_):
    run_training()


if __name__ == '__main__':
    tf.app.run()
