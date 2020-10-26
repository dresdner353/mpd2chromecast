#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import requests
import threading
import argparse
import time
import os
import sys
import cherrypy
import urllib
import json
import socket
import traceback

def log_message(message):
    print("%s %s" % (
        time.asctime(),
        message))
    sys.stdout.flush()

# Config inits
gv_cfg_filename = ""
gv_chromecast_name = ""

def get_chromecast():
    global gv_chromecast_name

    if not gv_chromecast_name:
        return None

    log_message("Connecting to Chromecast %s" % (gv_chromecast_name))
    devices, browser = pychromecast.get_listed_chromecasts(
            friendly_names=[gv_chromecast_name])

    if len(devices) > 0:
        log_message("Got device object.. uuid:%s model:%s" % (
            devices[0].uuid,
            devices[0].model_name))
        return devices[0]
    
    log_message("Failed to get device object")
    return None


def load_config():
    global gv_cfg_filename
    global gv_chromecast_name

    log_message("Loading config from %s" % (gv_cfg_filename))
    cfg_file = open(gv_cfg_filename, 'r')
    json_str = cfg_file.read()
    json_cfg = json.loads(json_str)
    cfg_file.close()

    gv_chromecast_name = json_cfg['chromecast']
    log_message("Set Chromecast device to [%s]" % (gv_chromecast_name))

    return


def config_init(name):
    global gv_chromecast_name
    global gv_cfg_filename

    gv_chromecast_name = name

    if (gv_chromecast_name == ""):
        # Determine home directory and cfg file
        # given no cmdline args used
        home = os.path.expanduser("~")
        gv_cfg_filename = home + '/.castrc'
        load_config()

    return


def config_agent():
    # monitor the config file and react on changes
    global gv_cfg_filename

    last_check = 0

    # 5-second check for config changes
    while (1):
        if os.path.exists(gv_cfg_filename):
            config_last_modified = os.path.getmtime(gv_cfg_filename)
            if config_last_modified > last_check:
                log_message("Detected update to %s" % (gv_cfg_filename))
                load_config()
                last_check = config_last_modified

        time.sleep(5)

    return 


# dummy stream handler object for cherrypy
class stream_handler(object):
    pass


def web_server():

    # engine config
    cherrypy.config.update({'environment': 'production',
                            'log.screen': False,
                            'log.access_file': '',
                            'log.error_file': ''})

    # Listen on our port on any IF
    cherrypy.server.socket_host = '0.0.0.0'
    cherrypy.server.socket_port = 8000

    # webhook for audio streaming
    # set up for directory serving
    # via /mnt
    web_conf = {
       '/music': {
           'tools.staticdir.on': True,
           'tools.staticdir.dir': '/mnt',
           'tools.staticdir.index': 'index.html',
       }
    }

    cherrypy.tree.mount(stream_handler(), '/', web_conf)

    # Cherrypy main loop blocking
    cherrypy.engine.start()
    cherrypy.engine.block()


def volumio_uri_to_url(server_ip,
                       uri):
    # Radio/external stream
    # uri will start with http
    if uri.startswith('http'):
        cast_url = uri
        type = "audio/mp3"
    else:
        # Format file URL as path from our web server
        cast_url = "http://%s:8000/music/%s" % (
                server_ip,
                uri)

        # Split out extension of file
        # probably not necessary as chromecast seems to work it
        # out itself
        file, ext = os.path.splitext(uri)
        type = "audio/%s" % (ext.replace('.', ''))

    return (cast_url, type)


def volumio_agent():
    global gv_server_ip
    global gv_chromecast_name
    global gv_verbose

    api_session = requests.session()

    cast_device = None # initial state
    cast_name = ""

    failed_status_update_count = 0

    # Cast state inits
    cast_status = 'none'
    cast_uri = 'none'
    cast_volume = 0

    last_volumio_seek = 0
    volumio_seek = 0
    
    while (1):
        # 1 sec delay per iteration
        time.sleep(1)
        print() # log output separator

        # Get status from Volumio
        try:
            resp = api_session.get('http://localhost:3000/api/v1/getstate')
            json_resp = resp.json()
            if gv_verbose:
                log_message(json.dumps(json_resp, indent = 4))
        except:
            log_message('Problem getting volumio status')
            continue

        status = json_resp['status']
        volumio_seek = int(json_resp['seek'] / 1000)
        last_volumio_seek = volumio_seek
        uri = json_resp['uri']
        volumio_volume = int(json_resp['volume']) / 100 # scale to 0.0 to 1.0 for Chromecast

        # optional fields depending on what 
        # is playing such as streams vs music files
        artist = 'None'
        album = 'None'
        title = 'None'
        duration = 0
        if 'artist' in json_resp:
            artist = json_resp['artist']
        if 'album' in json_resp:
            album = json_resp['album']
        if 'title' in json_resp:
            title = json_resp['title']
        if 'duration' in json_resp:
            duration = json_resp['duration']

        elapsed_mins = int(volumio_seek / 60)
        elapsed_secs = volumio_seek % 60
        duration_mins = int(duration / 60)
        duration_secs = duration % 60
        if duration > 0:
            progress = int(volumio_seek / duration * 100)
        else:
            progress = 0

        log_message("Current Track %s/%s/%s" % (
            artist,
            album,
            title))

        log_message("Volumio Status:%s Elapsed: %d:%02d/%d:%02d [%02d%%]" % (
            status,
            elapsed_mins,
            elapsed_secs,
            duration_mins,
            duration_secs,
            progress))

        # remove leading 'music-library' or 'mnt' if present
        # we're hosting from /mnt so we need remove the top-level
        # dir
        for prefix in ['music-library/', 'mnt/']:
            prefix_len = len(prefix)
            if uri.startswith(prefix):
                uri = uri[prefix_len:]

        # Chromecast URLs for media and artwork
        cast_url, type = volumio_uri_to_url(gv_server_ip, uri)
        #log_message("Stream URL:%s" % (cast_url))

        # Chromecast Status
        if (cast_device):

            # We need an updated status from the Chromecast
            # This can fail sometimes when nothing is really wrong and 
            # then other times when things are wrong :)
            #
            # So we give it a tolerance of 5 consecutive failures
            try:
                cast_device.media_controller.update_status()
                # Reset failed status count
                failed_status_update_count = 0
            except:
                failed_status_update_count += 1
                log_message("Failed to get chromecast status.. %d/5" % (
                    failed_status_update_count))

                if (failed_status_update_count >= 5):
                    log_message("Detected broken controller after 5 failures to get status")
                    cast_device = None
                    cast_status = 'none'
                    cast_uri = 'none'
                    cast_volume = 0
                    failed_status_update_count = 0
                    continue

            cast_elapsed = int(cast_device.media_controller.status.current_time)

            # Length and progress calculation
            if cast_device.media_controller.status.duration is not None:
                cast_duration = int(cast_device.media_controller.status.duration)
                cast_progress = int(cast_elapsed / cast_duration * 100)
            else:
                cast_duration = 0
                cast_progress = 0

            elapsed_mins = int(cast_elapsed / 60)
            elapsed_secs = cast_elapsed % 60
            duration_mins = int(cast_duration / 60)
            duration_secs = cast_duration % 60
            log_message("Chromecast Name:%s Status:%s Elapsed: %d:%02d/%d:%02d [%02d%%]" % (
                cast_name,
                status,
                elapsed_mins,
                elapsed_secs,
                duration_mins,
                duration_secs,
                cast_progress))


        # Configured Chromecast change
        # Clear existing device handle
        if cast_name != gv_chromecast_name:
            # Stop media player of existing device
            # if it exists
            if (cast_device):
                log_message("Detected Chromecast change from %s -> %s" % (
                    cast_name,
                    gv_chromecast_name))
                cast_device.media_controller.stop()
                cast_device.quit_app()
                cast_status = status
                cast_device = None
                continue

        # Get cast device when in play state and 
        # no device curently present
        if (status == 'play' and 
                not cast_device):
            cast_device = get_chromecast()
            cast_name = gv_chromecast_name

            if not cast_device:
                log_message("Failed to get cast device object")
                continue

            # Kill off any current app
            log_message("Waiting for device to get ready..")
            if not cast_device.is_idle:
                log_message("Killing current running app")
                cast_device.quit_app()

            while not cast_device.is_idle:
                time.sleep(1)

            # Cast state inits
            cast_status = 'none'
            cast_uri = 'none'
            cast_volume = 0
            continue


        # Volumio -> Chromecast Events
        # Anything that is driven from detecting changes
        # on the Volumio side and pushing to the Chromecast
        if (not cast_device):
            continue

        # Volume change only while playing
        if (cast_volume != volumio_volume and
                cast_status == 'play'):

            log_message("Setting Chromecast Volume: %.2f" % (volumio_volume))
            cast_device.set_volume(volumio_volume)
            cast_volume = volumio_volume
    
        # Pause
        if (cast_status != 'pause' and
            status == 'pause'):

            log_message("Pausing Chromecast")
            cast_device.media_controller.pause()
            cast_status = status
        
        # Resume play
        if (cast_status == 'pause' and 
            status == 'play'):

            log_message("Unpause Chromecast")
            cast_device.media_controller.play()
            cast_status = status
        
        # Stop
        if (cast_status != 'stop' and 
            status == 'stop'):

            log_message("Stop Chromecast")
            cast_device.media_controller.stop()
            cast_status = status
            cast_device = None
            continue

        # Play a song or stream or next in playlist
        if ((cast_status != 'play' and
            status == 'play') or
            (status == 'play' and uri != cast_uri)):

            log_message("Casting URL:%s type:%s" % (
                cast_url.encode('utf-8'),
                type))

            # Let the magic happen
            # Wait for the connection and then issue the 
            # URL to stream
            # current time option not vible as track name
            # changes before the seek data is updated
            cast_device.wait()
            cast_device.media_controller.play_media(
                    cast_url, 
                    content_type = type,
                    title = title,
                    #current_time = volumio_seek,
                    autoplay = True)

            # Note the various specifics of play 
            cast_status = status
            cast_uri = uri
            continue
    

        # Detect end of play on chromecast first
        if (status == 'play' and 
                cast_status == 'play' and
                cast_device.media_controller.status.player_is_idle):
            log_message("Chromecast idle.. Request Next song")
            resp = api_session.get('http://localhost:3000/api/v1/commands/?cmd=next')

        # Detect a skip on Volumio
        # and where the cast elapsed time > 0 (means it played at least 1 second)
        # and the difference between elapsed times >= 10 seconds
        if (status == 'play' and 
                cast_status == 'play' and 
                not cast_uri.startswith('http') and 
                cast_elapsed > 0 and 
                abs(volumio_seek - cast_elapsed) >= 10):
            log_message(
                    "Sync Volumio elapsed %d secs to Chromecast" % (
                        volumio_seek))
            cast_device.media_controller.seek(volumio_seek)
            continue 
    
        # Sync Chromecast playback back to Volumio
        # Every 10 seconds
        if (status == 'play' and 
                not cast_uri.startswith('http') and
                cast_elapsed > 0 and 
                cast_elapsed % 10 == 0):
                log_message(
                        "Sync Chromecast elapsed %d secs to Volumio" % (
                            cast_elapsed))
                resp = api_session.get(
                        'http://localhost:3000/api/v1/commands/?cmd=seek&position=%d' % (
                            cast_elapsed))



# main

parser = argparse.ArgumentParser(
        description='Volumio Chromecast Agent')

parser.add_argument('--name', 
                    help = 'Chromecast Friendly Name', 
                    default = "",
                    required = False)

parser.add_argument('--verbose', 
                    help = 'Enable verbose output', 
                    action = 'store_true')


args = vars(parser.parse_args())
gv_chromecast_name = args['name']
gv_verbose = args['verbose']

# Init config
config_init(gv_chromecast_name)

# Determine the main IP address of the server
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
gv_server_ip = s.getsockname()[0]
s.close()

# Thread management and main loop
thread_list = []

# Cherry Py web server
web_server_t = threading.Thread(target = web_server)
web_server_t.daemon = True
web_server_t.start()
thread_list.append(web_server_t)

# Volumio Agent
volumio_t = threading.Thread(target = volumio_agent)
volumio_t.daemon = True
volumio_t.start()
thread_list.append(volumio_t)

if (gv_cfg_filename != ""):
    # Config server thread if we're set to 
    # drive config from a file. that we we can 
    # handle updates
    config_t = threading.Thread(target = config_agent)
    config_t.daemon = True
    config_t.start()
    thread_list.append(config_t)

while (1):
    dead_threads = 0
    for thread in thread_list:
         if (not thread.isAlive()):
             dead_threads += 1

    if (dead_threads > 0):
        log_message("Detected %d dead threads.. exiting" % (dead_threads))
        sys.exit(-1);

    time.sleep(5)


