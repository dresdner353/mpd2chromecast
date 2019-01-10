#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import argparse
import os

# main

parser = argparse.ArgumentParser(
        description='Set Desired Chromecast')

parser.add_argument('--name', 
                    help = 'Chromecast Friendly Name', 
                    default = "",
                    required = False)

args = vars(parser.parse_args())
cast_name = args['name']

# Determine home directory
home = os.path.expanduser("~")

# Scan if no device specified
if (cast_name == ""):
    print("Discovering Chromecasts.. (this may take a while)")
    devices = pychromecast.get_chromecasts()
    total_devices = len(devices)
    print("Found %d devices" % (total_devices))
    if (total_devices > 0):
        index = 0
        for cc in devices:
            print("%2d   %s" % (index, cc.device.friendly_name))
            index += 1
    index = int(input("Enter device number: "))
    if (index < 0 or index >= total_devices):
        print("Invalid selection.. should be in range 0..%d" % (total_devices - 1))
    else:
        cast_name = devices[index].device.friendly_name

if cast_name != "":
    print("Setting desired Chromecast to [%s]" % (cast_name))
    env_file  = open(home + '/.castrc', 'w') 
    env_file.write('CHROMECAST="%s"\n' % (cast_name))
    env_file.close()
