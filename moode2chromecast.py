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


def load_config(cfg_filename):
    global gv_chromecast_name

    log_message("Loading config from %s" % (cfg_filename))
    cfg_file = open(cfg_filename, 'r')
    json_str = cfg_file.read()
    json_cfg = json.loads(json_str)
    cfg_file.close()

    gv_chromecast_name = json_cfg['chromecast']
    log_message("Set Chromecast device to [%s]" % (gv_chromecast_name))

    return


def config_agent():
    # monitor the config file and react on changes
    global gv_cfg_filename

    home = os.path.expanduser("~")
    gv_cfg_filename = home + '/.castrc'

    last_check = 0

    # 5-second check for config changes
    while (1):
        if os.path.exists(gv_cfg_filename):
            config_last_modified = os.path.getmtime(gv_cfg_filename)
            if config_last_modified > last_check:
                log_message("Detected update to %s" % (gv_cfg_filename))
                load_config(gv_cfg_filename)
                last_check = config_last_modified

        time.sleep(5)

    return 


def chromecast_agent():
    last_check = 0

    home = os.path.expanduser("~")
    discovered_devices_file = home + '/.castdevices'

    # 5-second check for config changes
    while (1):
        devices, browser = pychromecast.get_chromecasts()
        total_devices = len(devices)
        log_message("Discovered %d chromecasts" % (
            total_devices))

        index = 0
        f = open(discovered_devices_file, "w")
        for cc in devices:
            index += 1
            log_message("%d/%d %s" % (
                index, 
                total_devices,
                cc.device.friendly_name))
            f.write("%s\n" % (cc.device.friendly_name))

        f.close()

        # only repeat once every 60 seconds
        time.sleep(60)

    return 

# dummy stream handler object for cherrypy
class stream_handler(object):
    pass


def web_server():

    # engine config
    cherrypy.config.update(
            {
                'environment': 'production',
                'log.screen': False,
                'log.access_file': '',
                'log.error_file': ''
            }
            )

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


def moode_uri_to_url(
        server_ip,
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


def moode_albumart_to_url(
        server_ip,
        albumart):

    if albumart.startswith('http'):
        artwork_url = albumart
    else:
        # Format file URL as path to moode
        # webserver plus the freaky albumart URI
        artwork_url = "http://%s%s" % (
                server_ip,
                albumart)

    return artwork_url


def moode_agent():
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

    moode_elapsed = 0
    cast_timestamp = 0
    
    while (1):
        # 1 sec delay per iteration
        time.sleep(1)
        print() # log output separator
        now = int(time.time())

        # Get status from moOde
        try:
            resp = api_session.get('http://localhost/engine-mpd.php')
            json_resp = resp.json()
            if gv_verbose:
                log_message(json.dumps(json_resp, indent = 4))
        except:
            log_message('Problem getting moode status')
            continue

        # Start with the current playing/selected file
        uri = json_resp['file']
        if not uri:
            uri = ''

        moode_status = json_resp['state']
        moode_elapsed = json_resp['elapsed']
        if moode_elapsed:
            moode_elapsed = int(moode_elapsed)
        else:
            moode_elapsed = 0
        albumart = json_resp['coverurl']
        moode_volume = int(json_resp['volume']) / 100 # scale to 0.0 to 1.0 for Chromecast

        # optional fields depending on what 
        # is playing such as streams vs music files
        artist = ''
        album = ''
        title = ''
        duration = 0
        if 'artist' in json_resp:
            artist = json_resp['artist']
        if 'album' in json_resp:
            album = json_resp['album']
        if 'title' in json_resp:
            title = json_resp['title']
        if 'duration' in json_resp:
            duration = int(float(json_resp['duration']))

        # Elapsed time and progress
        elapsed_mins = int(moode_elapsed / 60)
        elapsed_secs = moode_elapsed % 60
        duration_mins = int(duration / 60)
        duration_secs = duration % 60
        if duration > 0:
            progress = int(moode_elapsed / duration * 100)
        else:
            progress = 0

        log_message("Current Track:%s/%s/%s" % (
            artist,
            album,
            title))

        log_message("moOde (%s) vol:%s %d:%02d/%d:%02d [%02d%%]" % (
            moode_status,
            int(moode_volume * 100),
            elapsed_mins,
            elapsed_secs,
            duration_mins,
            duration_secs,
            progress))

        # Chromecast URLs for media and artwork
        cast_url, type = moode_uri_to_url(gv_server_ip, uri)
        albumart_url = moode_albumart_to_url(gv_server_ip, albumart)

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
            log_message("%s (%s) vol:%02d %d:%02d/%d:%02d [%02d%%]" % (
                cast_name,
                cast_status,
                int(cast_volume * 100),
                elapsed_mins,
                elapsed_secs,
                duration_mins,
                duration_secs,
                cast_progress))


        # Configured Chromecast change
        # Clear existing device handle
        if (cast_name != gv_chromecast_name):
            # Stop media player of existing device
            # if it exists
            if (cast_device):
                log_message("Detected Chromecast change from %s -> %s" % (
                    cast_name,
                    gv_chromecast_name))
                cast_device.media_controller.stop()
                cast_device.quit_app()
                cast_status = moode_status
                cast_device = None
                continue

        # Get cast device when in play state and 
        # no device curently present
        if (moode_status == 'play' and 
                not cast_device):
            cast_device = get_chromecast()
            cast_name = gv_chromecast_name

            if not cast_device:
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


        # moOde -> Chromecast Events
        # Anything that is driven from detecting changes
        # on the moOde side and pushing to the Chromecast
        if (not cast_device):
            continue

        # Volume change only while playing
        if (cast_status == 'play' and 
                cast_volume != moode_volume):

            log_message("Setting Chromecast Volume: %.2f" % (moode_volume))
            cast_device.set_volume(moode_volume)
            cast_volume = moode_volume
            continue

        # Pause
        if (cast_status != 'pause' and
            moode_status == 'pause'):

            log_message("Pausing Chromecast")
            cast_device.media_controller.pause()
            cast_status = moode_status
            continue
        
        # Resume play
        if (cast_status == 'pause' and 
            moode_status == 'play'):

            log_message("Unpause Chromecast")
            cast_device.media_controller.play()
            cast_status = moode_status
            continue
        
        # Stop
        if (cast_status != 'stop' and 
            moode_status == 'stop'):

            log_message("Stop Chromecast")
            cast_device.media_controller.stop()
            cast_status = moode_status
            cast_device = None
            continue

        # Play a song or stream or next in playlist
        if ((cast_status != 'play' and
            moode_status == 'play') or
            (moode_status == 'play' and uri != cast_uri)):

            log_message("Casting URL:%s type:%s" % (
                cast_url.encode('utf-8'),
                type))

            # Let the magic happen
            # Wait for the connection and then issue the 
            # URL to stream
            cast_device.wait()
            cast_device.media_controller.play_media(
                    cast_url, 
                    content_type = type,
                    title = title,
                    thumb = albumart_url,
                    #current_time = moode_elapsed,
                    autoplay = True)

            # Seek playback on moOde to start of track
            # Had no success using the REST API for this
            # so I had to stoop to running mpc directly
            # Get the feeling however is that the moode API also
            # calls mpc
            os.system('mpc seek 0 >/dev/null 2>&1')

            # Note the various specifics of play 
            cast_status = moode_status
            cast_uri = uri
            cast_timestamp = now
            continue
    

        # Detect a skip on moOde and issue a seek request on the 
        # chromecast.
        # This feature can mis-fire depending on when its checked and 
        # what detail is present on the moOde status.
        # So we check that the chromecast is actively playing (cast_elapsed > 0)
        # Also check that there is a min of 3 seconds between the time the track was 
        # cast and curent timestamp. This prevents issues where the MPD status 
        # shows a new track but retains the old track elapsed time for 1-2 seconds
        # Finally we ensure there is at least 10 seconds difference between the 
        # two elapsed times to ensure it's not a false positive because of lag
        if (moode_status == 'play' and 
                cast_status == 'play' and 
                not cast_uri.startswith('http') and 
                cast_elapsed > 0 and 
                now - cast_timestamp > 3 and 
                abs(moode_elapsed - cast_elapsed) >= 10):
            log_message(
                    "Sync moOde elapsed %d secs to Chromecast" % (
                        moode_elapsed))
            cast_device.media_controller.seek(moode_elapsed)
            continue 
    
        # Every 10 seconds sync Chromecast playback 
        # back to moOde elapsed time if moode
        # is at the same time or further on.
        # Radio streams ignored for this.
        # The value we then set on moode is 1 second 
        # behind the # chromecast elapsed time.
        # We want moode preferentially 1 second behind the 
        # Chromecast to allow the chromecast complete the stream 
        # before it reacts to a track change
        if (moode_status == 'play' and 
                not cast_uri.startswith('http') and
                cast_elapsed > 0 and 
                cast_elapsed % 10 == 0 and
                moode_elapsed >= cast_elapsed):
                log_message(
                        "Sync Chromecast elapsed %d secs to moOde" % (
                            cast_elapsed))

                # Value for seek is 2 seconds less
                # selecting 1 second seems to get it too close to the cast
                # elapsed.. we want 1-2 seconds behind
                os.system('mpc seek %d >/dev/null 2>&1' % (cast_elapsed - 2))

# main

parser = argparse.ArgumentParser(
        description='moOde Chromecast Agent')

parser.add_argument('--verbose', 
                    help = 'Enable verbose output', 
                    action = 'store_true')


args = vars(parser.parse_args())
gv_verbose = args['verbose']

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

# moOde Agent
moode_t = threading.Thread(target = moode_agent)
moode_t.daemon = True
moode_t.start()
thread_list.append(moode_t)

# Config Agent
config_t = threading.Thread(target = config_agent)
config_t.daemon = True
config_t.start()
thread_list.append(config_t)

# Chromecast Agent
chromecast_t = threading.Thread(target = chromecast_agent)
chromecast_t.daemon = True
chromecast_t.start()
thread_list.append(chromecast_t)

while (1):
    dead_threads = 0
    for thread in thread_list:
         if (not thread.isAlive()):
             dead_threads += 1

    if (dead_threads > 0):
        log_message("Detected %d dead threads.. exiting" % (dead_threads))
        sys.exit(-1);

    time.sleep(5)


