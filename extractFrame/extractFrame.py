# 将视频文件转换为RGB和光流
import concurrent.futures
import datetime
import os
import random
import subprocess


# 列出所有文件
def list_all_files(root_dir):
    _files = []
    list = os.listdir(root_dir)
    for i in range(len(list)):
        path = os.path.join(root_dir, list[i])
        if os.path.isdir(path):
            _files.extend(list_all_files(path))
        if os.path.isfile(path):
            _files.append(path)

    return _files


# 处理一个视频文件
def convert_one_video_to_frame(file, dir_path, device_id):
    # 转换为RGB和光流
    subprocess.call(
        'denseFlow_gpu -f {0} -x {1}/x/x -y {1}/y/y -i {1}/i/i -b 20 -t 1 -d {2} -s 1 -h 0 -w 0'.format(file, dir_path,
                                                                                                        device_id),
        shell=True)
    print('处理完成 {} {}'.format(datetime.datetime.now(), file))


def main():
    start_date = datetime.datetime.now()
    root_dir = os.path.join(os.getcwd(), '..', 'data/UCF-101')
    files = list_all_files(root_dir)
    with concurrent.futures.ProcessPoolExecutor(max_workers=12) as executor:
        for file in files:
            # 保存frame文件的文件夹
            dir_path = file[:file.rfind('.')]
            if not os.path.exists(dir_path):
                os.mkdir(dir_path)
            # 将rbg和光流分到不同的文件夹存储
            for flag in ['i', 'x', 'y']:
                new_dir_path = os.path.join(dir_path, flag)
                if not os.path.exists(new_dir_path):
                    os.mkdir(new_dir_path)
            device_id = random.randint(1, 3)
            executor.submit(convert_one_video_to_frame, file, dir_path, device_id)

    end_date = datetime.datetime.now()
    print('开始结束时间{} {}'.format(start_date, end_date))
    print('处理完成，程序运行时长为 {} 秒'.format((end_date - start_date).seconds))


if __name__ == '__main__':
    main()
