#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import mpd
import requests
import threading
import argparse
import time
import os
import sys
import cherrypy
import json
import socket


def log_message(message):
    print("%s %s" % (
        time.asctime(),
        message))
    sys.stdout.flush()

# Config inits
gv_cfg_filename = ""
gv_chromecast_name = ""
gv_cast_port = 8080
gv_streamer_variant = "Unknown"


def determine_streamer_variant():
    # Determine the stream variant we have
    # as some variations apply in how things work

    global gv_streamer_variant

    if (os.path.exists('/usr/local/bin/moodeutl') or
            os.path.exists('/usr/bin/moodeutl')):
        gv_streamer_variant = 'moOde'

    elif (os.path.exists('/usr/local/bin/volumio') or
            os.path.exists('/usr/bin/volumio')):
        gv_streamer_variant = 'Volumio'

    log_message('Streamer is identified as %s' % (
        gv_streamer_variant))



def get_chromecast():
    global gv_chromecast_name

    if (not gv_chromecast_name or 
            gv_chromecast_name == 'off'):
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

    discovered_devices_file = '/tmp/castdevices'

    # 1-minute interval for chromecast scan
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
    global gv_cast_port

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
    cherrypy.server.socket_port = gv_cast_port

    # webhook for audio streaming
    # set up for directory serving
    # via /mnt
    web_conf = {
       '/music': {
           'tools.staticdir.on': True,
           'tools.staticdir.dir': '/mnt',
           'tools.staticdir.index': 'index.html',
       },
       '/tmp': {
           'tools.staticdir.on': True,
           'tools.staticdir.dir': '/tmp',
           'tools.staticdir.index': 'index.html',
       }
    }

    cherrypy.tree.mount(stream_handler(), '/', web_conf)

    # Cherrypy main loop blocking
    cherrypy.engine.start()
    cherrypy.engine.block()


def mpd_file_to_url(mpd_file):
    global gv_server_ip
    global gv_cast_port

    # Radio/external stream
    # URL will start with http
    if mpd_file.startswith('http'):
        cast_url = mpd_file
        type = "audio/mp3"
    else:
        # Format file URL as path from our web server
        cast_url = "http://%s:%d/music/%s" % (
                gv_server_ip,
                gv_cast_port,
                mpd_file)

        # Split out extension of file
        # probably not necessary as chromecast seems to work it
        # out itself
        file, ext = os.path.splitext(mpd_file)
        type = "audio/%s" % (ext.replace('.', ''))

    return (cast_url, type)


def get_artwork_url():
    global gv_server_ip
    global gv_cast_port
    global gv_streamer_variant

    artwork_url = None
    api_session = requests.session()

    if gv_streamer_variant == 'moOde':
        try:
            resp = api_session.get('http://localhost/engine-mpd.php')
            json_resp = resp.json()
            if gv_verbose:
                log_message(json.dumps(json_resp, indent = 4))

            albumart = json_resp['coverurl']
            artwork_url = "http://%s%s" % (
                    gv_server_ip,
                    albumart)
        except:
            log_message('Problem getting moode status for artwork')


    elif gv_streamer_variant == 'Volumio':
        try:
            resp = api_session.get('http://localhost:3000/api/v1/getstate')
            json_resp = resp.json()
            if gv_verbose:
                log_message(json.dumps(json_resp, indent = 4))

            albumart = json_resp['albumart']
            artwork_url = "http://%s:3001%s" % (
                   server_ip,
                   albumart)
        except:
            log_message('Problem getting volumio status for artwork')


    return artwork_url


def mpd_agent():
    global gv_server_ip
    global gv_chromecast_name
    global gv_verbose

    mpd_client = None
    cast_device = None # initial state
    cast_name = ""

    failed_status_update_count = 0

    # Cast state inits
    cast_status = 'none'
    cast_file = 'none'
    cast_volume = 0

    mpd_elapsed = 0

    cast_confirmed = False
    
    while (1):
        # 1 sec delay per iteration
        time.sleep(1)
        print() # log output separator
        now = int(time.time())

        if not mpd_client:
            mpd_client = mpd.MPDClient()
            mpd_client.connect("localhost", 6600)

        # Get current MPD status details
        try:
            mpd_client_status = mpd_client.status()
            mpd_client_song = mpd_client.currentsong()
            if gv_verbose:
                log_message('MPD Status:\n%s' % (
                    json.dumps(
                        mpd_client_status, 
                        indent = 4)))
                log_message('MPD Current Song:\n%s' % (
                    json.dumps(
                        mpd_client_song, 
                        indent = 4)))
        except:
            # reset.. and let next loop reconect
            log_message('Problem getting mpd status')
            mpd_client = None
            continue

        # Start with the current playing/selected file
        mpd_file = 'none'
        if ('file' in mpd_client_song and 
                mpd_client_song['file']):
            mpd_file = mpd_client_song['file']

        # mandatory fields
        mpd_status = mpd_client_status['state']
        mpd_volume = int(mpd_client_status['volume']) / 100 

        # optionals (will depend on given state and stream vs file
        mpd_elapsed = 0
        mpd_duration = 0

        if 'elapsed' in mpd_client_status:
            mpd_elapsed = int(float(mpd_client_status['elapsed']))
        if 'duration' in mpd_client_status:
            mpd_duration = int(float(mpd_client_status['duration']))


        artist = ''
        album = ''
        title = ''
        if 'artist' in mpd_client_song:
            artist = mpd_client_song['artist']
        if 'album' in mpd_client_song:
            album = mpd_client_song['album']
        if 'title' in mpd_client_song:
            title = mpd_client_song['title']

        # Elapsed time and progress
        elapsed_mins = int(mpd_elapsed / 60)
        elapsed_secs = mpd_elapsed % 60
        duration_mins = int(mpd_duration / 60)
        duration_secs = mpd_duration % 60
        if mpd_duration > 0:
            progress = int(mpd_elapsed / mpd_duration * 100)
        else:
            progress = 0

        log_message("Current Track:%s/%s/%s" % (
            artist,
            album,
            title))

        log_message("MPD (%s) vol:%s %d:%02d/%d:%02d [%02d%%]" % (
            mpd_status,
            int(mpd_volume * 100),
            elapsed_mins,
            elapsed_secs,
            duration_mins,
            duration_secs,
            progress))

        # Chromecast URLs for media and artwork
        cast_url, cast_file_type = mpd_file_to_url(mpd_file)

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
                    cast_file = 'none'
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
                cast_status = mpd_status
                cast_device = None
                continue

        # Get cast device when in play state and 
        # no device curently present
        if (mpd_status == 'play' and 
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
            cast_file = 'none'
            cast_volume = 0
            continue


        # MPD -> Chromecast Events
        # Anything that is driven from detecting changes
        # on the MPD side and pushing to the Chromecast
        if (not cast_device):
            continue

        # Initial Cast protection
        # In first 10 seconds after casting a file
        # we keep MPD paused only unpausing 
        # and re-seeking to cast_elapsed - 1 when the 
        # chromecast is reporting elapsed time
        if (not cast_confirmed and 
                mpd_status == 'pause' and 
                cast_status == 'play' and
                not cast_file.startswith('http')):
            if (cast_elapsed < 1):
                log_message('Initial cast.. Waiting for chromecast elapsed time')
            else:
                log_message('Initial cast.. Unpausing mpd')
                # sync 1 second behind
                mpd_client.seekcur(cast_elapsed - 1)
                # play (pause 0)
                mpd_client.pause(0)
                cast_confirmed = True
            continue


        # Volume change only while playing
        if (cast_status == 'play' and 
                cast_volume != mpd_volume):

            log_message("Setting Chromecast Volume: %.2f" % (mpd_volume))
            cast_device.set_volume(mpd_volume)
            cast_volume = mpd_volume
            continue

        # Pause
        if (cast_status != 'pause' and
            mpd_status == 'pause'):

            log_message("Pausing Chromecast")
            cast_device.media_controller.pause()
            cast_status = mpd_status
            continue
        
        # Resume play
        if (cast_status == 'pause' and 
            mpd_status == 'play'):

            log_message("Unpause Chromecast")
            cast_device.media_controller.play()
            cast_status = mpd_status
            continue
        
        # Stop
        if (cast_status != 'stop' and 
            mpd_status == 'stop'):

            log_message("Stop Chromecast")
            cast_device.media_controller.stop()
            cast_status = mpd_status
            cast_device = None
            continue

        # Play a song or stream or next in playlist
        if ((cast_status != 'play' and
            mpd_status == 'play') or
            (mpd_status == 'play' and mpd_file != cast_file)):

            log_message("Casting URL:%s type:%s" % (
                cast_url.encode('utf-8'),
                cast_file_type))

            args = {}
            args['content_type'] = cast_file_type
            args['title'] = title
            args['autoplay'] = True

            artwork_url = get_artwork_url()
            if artwork_url:
                args['thumb'] = artwork_url
                log_message("Artwork URL:%s" % (
                    artwork_url))

            # Let the magic happen
            # Wait for the connection and then issue the 
            # URL to stream
            cast_device.wait()
            cast_device.media_controller.play_media(
                    cast_url, 
                    **args)

            # Note the various specifics of play 
            cast_status = mpd_status
            cast_file = mpd_file

            # Pause and seek to start of track
            # only applies to local files
            if (not cast_file.startswith('http')):
                log_message("Pausing MPD")
                mpd_client.pause(1)
                mpd_client.seekcur(0)
                cast_confirmed = False

            continue
    

        # Detect a skip on MPD and issue a seek request on the 
        # chromecast.
        # This feature can mis-fire depending on when its checked and 
        # what detail is present on the MPD status.
        # So we check that the chromecast is actively playing (cast_elapsed > 0)
        # Also check that there is a min of 3 seconds between the time the track was 
        # cast and curent timestamp. This prevents issues where the MPD status 
        # shows a new track but retains the old track elapsed time for 1-2 seconds
        # Finally we ensure there is at least 10 seconds difference between the 
        # two elapsed times to ensure it's not a false positive because of lag
        if (mpd_status == 'play' and 
                cast_status == 'play' and 
                not cast_file.startswith('http') and 
                cast_confirmed and
                abs(mpd_elapsed - cast_elapsed) >= 10):
            log_message(
                    "Sync MPD elapsed %d secs to Chromecast" % (
                        mpd_elapsed))
            cast_device.media_controller.seek(mpd_elapsed)
            continue 
    
        # Every 10 seconds sync Chromecast playback 
        # back to MPD elapsed time if mpd
        # is at the same time or further on.
        # Radio streams ignored for this.
        # The value we then set on mpd is 1 second 
        # behind the # chromecast elapsed time.
        # We want mpd preferentially 1 second behind the 
        # Chromecast to allow the chromecast complete the stream 
        # before it reacts to a track change
        if (mpd_status == 'play' and 
                not cast_file.startswith('http') and
                cast_elapsed > 0 and 
                cast_elapsed % 10 == 0 and
                (mpd_elapsed >= cast_elapsed or
                    mpd_elapsed < cast_elapsed - 1)):
                log_message(
                        "Sync Chromecast elapsed %d secs to MPD" % (
                            cast_elapsed))

                # Value for seek is 1 second behind
                mpd_client.seekcur(cast_elapsed - 1)

# main

parser = argparse.ArgumentParser(
        description='MPD Chromecast Agent')

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

# Determine variant
determine_streamer_variant()

# Thread management and main loop
thread_list = []

# Cherry Py web server
web_server_t = threading.Thread(target = web_server)
web_server_t.daemon = True
web_server_t.start()
thread_list.append(web_server_t)

# MPD Agent
mpd_t = threading.Thread(target = mpd_agent)
mpd_t.daemon = True
mpd_t.start()
thread_list.append(mpd_t)

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


