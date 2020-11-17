#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import zeroconf
import mpd
import requests
import urllib
import threading
import argparse
import time
import os
import sys
import cherrypy
import json
import socket
import pathlib


def log_message(message):
    print("%s %s" % (
        time.asctime(),
        message))
    sys.stdout.flush()

# Config inits
gv_cfg_filename = ""
gv_chromecast_name = ""
gv_cast_port = 8090
gv_platform_variant = "Unknown"

# Discovered Chromecasts dict
# and related zconf object
gv_discovered_devices = {}
gv_zconf = None

# Fixed MPD music location
# may make this configurable in time
gv_mpd_music_dir = '/var/lib/mpd/music'

# Global MPD agent deadlock timestamp
gv_mpd_agent_timestamp = 0

# global handles on MPD client
gv_mpd_client = None
gv_mpd_client_status = None
gv_mpd_client_song = None
gv_mpd_playlists = None
gv_mpd_queue = None

def determine_platform_variant():
    # Determine the stream variant we have
    # as some variations apply in how things work

    global gv_platform_variant

    if (os.path.exists('/usr/local/bin/moodeutl') or
            os.path.exists('/usr/bin/moodeutl')):
        gv_platform_variant = 'moOde'

    elif (os.path.exists('/usr/local/bin/volumio') or
            os.path.exists('/usr/bin/volumio')):
        gv_platform_variant = 'Volumio'

    log_message('Platform is identified as %s' % (
        gv_platform_variant))



def get_chromecast(name):
    global gv_discovered_devices
    global gv_zconf

    if (not name or 
            name == 'Disabled'):
        return None

    log_message("Looking up Chromecast %s" % (name))

    if not gv_zconf:
        log_message("No zconf service active")
        return None

    if not name in gv_discovered_devices:
        log_message("chromecast not found in discovered device services")
        return None

    try:
        log_message("Getting chromecast device object")
        # Get the device handle
        # FIXME this call has issues
        device = pychromecast.get_chromecast_from_service(
                gv_discovered_devices[name],
                gv_zconf)
    except:
        log_message("Failed to chromecast device object")
        device = None

    return device


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
    global gv_discovered_devices
    global gv_zconf

    def chromecast_add_callback(uuid, name):
        # Add discovered device to global dict
        # keyed on friendly name and stores the full 
        # service record
        friendly_name = cast_listener.services[uuid][3]
        gv_discovered_devices[friendly_name] = cast_listener.services[uuid]

    def chromecast_remove_callback(uuid, name, service):
        # purge removed devices from the global dict
        friendly_name = cast_listener.services[uuid][3]
        if friendly_name in gv_discovered_devices:
            del gv_discovered_devices[friendly_name]

    cast_listener = pychromecast.CastListener(
            chromecast_add_callback,
            chromecast_remove_callback)

    gv_zconf = zeroconf.Zeroconf()
    cast_browser = pychromecast.discovery.start_discovery(
            cast_listener, 
            gv_zconf)

    while (1):
        time.sleep(30)
        log_message('Discovered cast devices: %s' % (
            list(gv_discovered_devices.keys())))

    return 


def build_cast_web_page():
    global gv_discovered_devices
    global gv_chromecast_name
    global gv_mpd_client_status
    global gv_mpd_client_song
    global gv_mpd_playlists
    global gv_mpd_queue

    web_page_tmpl = """
        <head>   
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
        <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.bundle.min.js"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          .material-icons.md-18 { font-size: 18px; }
          .material-icons.md-24 { font-size: 24px; }
          .material-icons.md-36 { font-size: 36px; }
          .material-icons.md-48 { font-size: 48px; }

        </style>
        <title>__TITLE__</title>

        <script>
            // enable tooltips
            $(function () {
                $('[data-toggle="tooltip"]').tooltip()
            })

        $(document).ready(function(){
        __ACTION_FUNCTIONS__
        });

        // Window focus awareness
        // for refresh page behaviour
        var window_focus = true;

        $(window).focus(function() {
            window_focus = true;
        }).blur(function() {
            window_focus = false;
        });

        // refresh timer and function
        // We use an interval refresh which will be called
        // every __RELOAD__ msecs and will invoke a reload of 
        // data into the dashboard div if the window is in focus
        // If not, we will skip the reload.
        // We also cancel the timer ahead of calling the reload to 
        // avoid the reload stacking more timers on itself and 
        // causing major issues
        var refresh_timer = setInterval(refreshPage, __RELOAD__);
        
        function refreshPage() {
            if (window_focus == true) {
                $.get("__REFRESH_URL__", function(data, status){
                    clearInterval(refresh_timer);
                    $("#dashboard").html(data);
                });
            }
        }

        </script>
        </head>   
        <body>
            <div id="dashboard">__DASHBOARD__</div>
        </body>
    """

    click_get_reload_template = """
        $("#__ID__").click(function(){
            $.get('/cast?__ARG__=__VAL__', function(data, status) {
                // clear refresh timer before reload
                clearInterval(refresh_timer);
                $("#dashboard").html(data);
            });
        });

        $('#__ID__').on('click', function() {
          // opened combo.. set refresh to a longer interval
          clearInterval(refresh_timer);
          refresh_timer = setInterval(refreshPage, 120000);
        })
    """

    change_get_reload_template = """
        $('#__ID__').on('change', function() {
            $.get('/cast?__ID__=' + this.value, function(data, status) {
                // clear refresh timer before reload
                clearInterval(refresh_timer);
                $("#dashboard").html(data);
            });
        });

        $('#__ID__').on('click', function() {
          // opened combo.. set refresh to a longer interval
          clearInterval(refresh_timer);
          refresh_timer = setInterval(refreshPage, 120000);
        })
    """


    dashboard_str = ""
    jquery_str = ""

    # main container and card
    dashboard_str += (
            '<div class="container-fluid">'
            '<div class="card">'
            '<div class="card-body">'
            ) 

    dashboard_str += (
            '<div class="input-group mb-3">'
            '<i class="material-icons md-36">%s</i>&nbsp;'
            '<select class="custom-select custom-select" id="chromecast" name="chromecast">'
            ) % (
                    'cast_connected' if gv_chromecast_name != 'Disabled' else 'cast'
                    )

    # Construct a sorted list of discovered device names
    # and put 'Disabled' at the top
    device_list = ['Disabled']
    device_list += sorted(list(gv_discovered_devices.keys()))

    for device in device_list:
        if device == gv_chromecast_name:
            selected_str = 'selected'
        else:
            selected_str = ''
        dashboard_str += (
                '<option value="%s" %s>%s</option>' % (
                    device, 
                    selected_str, 
                    device)
                )

    # Chromecast combo box end
    dashboard_str += (
            '</select>'
            '</div>'
            )

    # action code for selecting a device
    action_str = change_get_reload_template
    action_str = action_str.replace('__ID__', 'chromecast')
    jquery_str += action_str

    # Playlists
    if (gv_mpd_playlists and
            len(gv_mpd_playlists) > 0):

        dashboard_str += (
                '<div class="input-group mb-3">'
                '<i class="material-icons md-36">playlist_play</i>&nbsp;'
                '<select class="custom-select custom-select" id="playlist" name="playlist">'
                ) 

        # Construct a list of playlists
        dashboard_str += (
                '     <option value="None">Select Playlist</option>' 
                )
        for item in gv_mpd_playlists:
            dashboard_str += (
                    '     <option value="%s">%s</option>' % (
                        item['playlist'], 
                        item['playlist'])
                    )

        # playlist combo box end 
        dashboard_str += (
                '</select>'
                '</div>'
                )

        # action code for selecting a playlist
        action_str = change_get_reload_template
        action_str = action_str.replace('__ID__', 'playlist')
        jquery_str += action_str

    # Queue (current playlist)
    if (gv_mpd_queue and
            len(gv_mpd_queue) > 0):

        dashboard_str += (
                '<div class="input-group mb-3">'
                '<i class="material-icons md-36">queue_music</i>&nbsp;'
                '<select class="custom-select custom-select" id="song" name="song">'
                ) 

        # Construct a list of songs
        dashboard_str += (
                '<option value="None">Select Track</option>' 
                )
        i = -1
        for item in gv_mpd_queue:
            i += 1
            if 'artist' in item and 'title' in item:
                queue_title = '%s - %s' % (
                        item['artist'],
                        item['title'])
            elif 'name' in item:
                queue_title = '%s' % (
                        item['name'])
            else:
                queue_title = 'Unknown'

            dashboard_str += (
                    '<option value="%d">%s</option>' % (
                        i,
                        queue_title,
                        )
                    )

        # playlist combo box end 
        dashboard_str += (
                '</select>'
                '</div>'
                )

        # action code for selecting a track from queue
        action_str = change_get_reload_template
        action_str = action_str.replace('__ID__', 'song')
        jquery_str += action_str    

    # MPD Playback
    if gv_mpd_client_status:
        # material icon.. play by default and pause if playing
        playback_icon_ref = 'play_circle_filled'
        if (gv_mpd_client_status and 
                gv_mpd_client_status['state'] == 'play'):
            playback_icon_ref = 'pause_circle_filled'

        # MPD Volume
        mpd_volume = int(gv_mpd_client_status['volume'])
        mpd_random = int(gv_mpd_client_status['random'])
        mpd_repeat = int(gv_mpd_client_status['repeat'])

        dashboard_str += (
                '<div class="input-group mb-3">'
                '<button id="prev" type="button" class="btn btn-primary">'
                '<i class="material-icons md-36">skip_previous</i></button>'
                '&nbsp;'
                '<button id="prev30" type="button" class="btn btn-primary">'
                '<i class="material-icons md-36">replay_30</i></button>'
                '&nbsp;'
                '<button id="play" type="button" class="btn btn-primary">'
                '<i class="material-icons md-36">%s</i></button>'
                '&nbsp;'
                '<button id="next30" type="button" class="btn btn-primary">'
                '<i class="material-icons md-36">forward_30</i></button>'
                '&nbsp;'
                '<button id="next" type="button" class="btn btn-primary">'
                '<i class="material-icons md-36">skip_next</i></button>'
                '</div>'
                '<div class="input-group mb-3">'
                '<button id="shuffle" type="button" class="btn btn-%s">'
                '<i class="material-icons md-36">shuffle</i></button>'
                '&nbsp;'
                '<button id="repeat" type="button" class="btn btn-%s">'
                '<i class="material-icons md-36s">repeat</i></button>'
                '&nbsp;'
                '<button id="voldown" type="button" class="btn btn-primary">'
                '<i class="material-icons md-36">volume_down</i></button>'
                '&nbsp;'
                '<button id="volume" type="button" class="btn btn-primary">'
                '%02d</button>'
                '&nbsp;'
                '<button id="volup" type="button" class="btn btn-primary">'
                '<i class="material-icons md-36">volume_up</i></button>'
                '</div>'
                ) % (
                        playback_icon_ref,
                        'primary' if mpd_random else 'secondary',
                        'primary' if mpd_repeat else 'secondary',
                        mpd_volume,
                        )

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'prev')
        action_str = action_str.replace('__ARG__', 'playback')
        action_str = action_str.replace('__VAL__', 'prev')
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'prev30')
        action_str = action_str.replace('__ARG__', 'seek')
        action_str = action_str.replace('__VAL__', '-30')
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'play')
        action_str = action_str.replace('__ARG__', 'playback')
        action_str = action_str.replace('__VAL__', 'play')
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'next30')
        action_str = action_str.replace('__ARG__', 'seek')
        action_str = action_str.replace('__VAL__', '%2b30')
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'next')
        action_str = action_str.replace('__ARG__', 'playback')
        action_str = action_str.replace('__VAL__', 'next')
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'voldown')
        action_str = action_str.replace('__ARG__', 'volume')
        action_str = action_str.replace('__VAL__', str(mpd_volume - 5))
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'volup')
        action_str = action_str.replace('__ARG__', 'volume')
        action_str = action_str.replace('__VAL__', str(mpd_volume + 5))
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'shuffle')
        action_str = action_str.replace('__ARG__', 'shuffle')
        action_str = action_str.replace('__VAL__', str((mpd_random + 1) % 2))
        jquery_str += action_str

        action_str = click_get_reload_template
        action_str = action_str.replace('__ID__', 'repeat')
        action_str = action_str.replace('__ARG__', 'repeat')
        action_str = action_str.replace('__VAL__', str((mpd_repeat + 1) % 2))
        jquery_str += action_str

        # Albumart and curent track details
        if (gv_mpd_client_song and 
                'file' in gv_mpd_client_song):
            albumart_url = get_albumart_url(gv_mpd_client_song['file'])
            if albumart_url:
                dashboard_str += (
                        '<img class="card-img-top" src="%s" alt="album art">'
                        '<br>'
                        '<br>'
                        '<center>'
                        '<h4 class="card-title">%s</h4>'
                        '<h5 class="card-subitle mb-2 text-muted">%s - %s</h5>'
                        '</center>'
                        ) % (
                                albumart_url,
                                gv_mpd_client_song['title'],
                                gv_mpd_client_song['artist'],
                                gv_mpd_client_song['album'],
                                )
    else:
        # no status
        # just report something
        dashboard_str += (
                '<br>'
                '<center>'
                '<h4 class="card-title">Updating...</h4>'
                '</center>'
                ) 

    # Close outer dv
    dashboard_str += (
            '</div>'
            '</div>'
            '</div>'
            )

    web_page_str = web_page_tmpl
    web_page_str = web_page_str.replace("__TITLE__", "mpd2chromecast Control Panel")
    web_page_str = web_page_str.replace("__ACTION_FUNCTIONS__", jquery_str)
    web_page_str = web_page_str.replace("__DASHBOARD__", dashboard_str)
    web_page_str = web_page_str.replace("__REFRESH_URL__", "/cast")
    web_page_str = web_page_str.replace("__RELOAD__", "10000")

    return web_page_str


# dummy stream handler object for cherrypy
class stream_handler(object):
    pass


class cast_handler(object):
    @cherrypy.expose()

    def index(
            self, 
            chromecast = None, 
            playback = None, 
            seek = None, 
            volume = None, 
            playlist = None, 
            song = None,
            shuffle = None,
            repeat = None):

        global gv_chromecast_name
        global gv_mpd_client
        global gv_mpd_client_status

        log_message("/cast API %s params:%s" % (
            cherrypy.request.remote.ip,
            cherrypy.request.params))

        if chromecast:
            log_message('/cast chromecast -> %s' % (
                chromecast))

            # Make change instantly
            gv_chromecast_name = chromecast

            # Also update config to make chanfge persistent
            home = os.path.expanduser("~")
            cfg_file = open(home + '/.castrc', 'w') 
            json_cfg = {}
            json_cfg['chromecast'] = chromecast
            cfg_file.write('%s\n' % (json.dumps(json_cfg)))
            cfg_file.close()

        if playback:
            log_message('/cast playback %s' % (
                playback))
            if gv_mpd_client:
                if playback == 'prev':
                    gv_mpd_client.previous()
                elif playback == 'next':
                    gv_mpd_client.next()
                elif playback == 'play':
                    # doubles as play/pause toggle
                    gv_mpd_client.pause()

                    # best effort sly toggle on state
                    # ro get returned web content updated
                    if gv_mpd_client_status:
                        if gv_mpd_client_status['state'] == 'play':
                            gv_mpd_client_status['state'] = 'pause'
                        else:
                            gv_mpd_client_status['state'] = 'play'

        if seek:
            log_message('/cast seek %s' % (
                seek))
            if gv_mpd_client:
                gv_mpd_client.seekcur(seek)


        if volume:
            log_message('/cast volume %s' % (
                volume))
            if gv_mpd_client:
                gv_mpd_client.setvol(volume)

                if gv_mpd_client_status:
                    gv_mpd_client_status['volume'] = volume

        if playlist:
            log_message('/cast playlist %s' % (
                playlist))
            if gv_mpd_client:
                gv_mpd_client.clear()
                gv_mpd_client.load(playlist)
                gv_mpd_client.play(0)

        if song:
            log_message('/cast song %s' % (
                playlist))
            if gv_mpd_client:
                gv_mpd_client.play(int(song))

        if shuffle:
            log_message('/cast shuffle %s' % (
                shuffle))
            if gv_mpd_client:
                gv_mpd_client.random(int(shuffle))

                if gv_mpd_client_status:
                    gv_mpd_client_status['random'] = shuffle

        if repeat:
            log_message('/cast repeat %s' % (
                repeat))
            if gv_mpd_client:
                gv_mpd_client.repeat(int(repeat))

                if gv_mpd_client_status:
                    gv_mpd_client_status['repeat'] = repeat

        return build_cast_web_page()

    # Force trailling slash off on called URL
    index._cp_config = {'tools.trailing_slash.on': False}


def web_server():
    global gv_cast_port
    global gv_mpd_music_dir

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
    # via /var/lib/mpd/music
    stream_conf = {
        '/music' : {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': gv_mpd_music_dir,
            'tools.staticdir.index': 'index.html',
        }
    }

    # Nothing special in play for the /cast API
    cast_conf = {}

    cherrypy.tree.mount(stream_handler(), '/', stream_conf)
    cherrypy.tree.mount(cast_handler(), '/cast', cast_conf)

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
        # mpd_file path is also made web-safe
        cast_url = "http://%s:%d/music/%s" % (
                gv_server_ip,
                gv_cast_port,
                urllib.parse.quote(mpd_file))

        # Split out extension of file
        # probably not necessary as chromecast seems to work it
        # out itself
        file, ext = os.path.splitext(mpd_file)
        type = "audio/%s" % (ext.replace('.', ''))

    return (cast_url, type)


def get_albumart_url(mpd_file):
    global gv_server_ip
    global gv_cast_port
    global gv_verbose

    # Ignore URLs
    if mpd_file.startswith('http'):
        return None

    art_names = [
            'cover.png',
            'cover.jpg',
            'cover.tiff',
            'cover.bmp',
            'cover.gif',
            ]

    albumart_url = None

    mpd_rel_path = pathlib.Path(mpd_file)
    mpd_full_path = pathlib.Path(gv_mpd_music_dir + '/' + mpd_file)

    for name in art_names:
        cover_file = str(mpd_full_path.parent / name)
        cover_rel_file = str(mpd_rel_path.parent / name)
        if os.path.exists(cover_file):
            albumart_url = "http://%s:%d/music/%s" % (
                    gv_server_ip,
                    gv_cast_port,
                    urllib.parse.quote(cover_rel_file))
            break

    return albumart_url


def mpd_agent():
    global gv_server_ip
    global gv_chromecast_name
    global gv_verbose
    global gv_mpd_agent_timestamp
    global gv_mpd_client
    global gv_mpd_client_status
    global gv_mpd_client_song
    global gv_mpd_playlists
    global gv_mpd_queue

    now = int(time.time())

    # MPD inits
    gv_mpd_client = None
    mpd_last_status = now

    # Cast state inits
    cast_device = None # initial state
    cast_name = ""
    cast_status = 'none'
    cast_file = 'none'
    cast_volume = 0
    cast_confirmed = False
    cast_failed_update_count = 0
    cast_last_status = now
    
    while (1):
        # 1 sec delay per iteration
        time.sleep(1)

        print() # log output separator
        now = int(time.time())

        # Timestamp loop activity for MPD agent
        # acts as a deadlock detection in main loop
        gv_mpd_agent_timestamp = now

        # MPD healthcheck
        if now - mpd_last_status > 60:
            log_message("No MPD contact in 60 seconds... exiting")
            return

        if not gv_mpd_client:
            log_message('Connecting to MPD...')
            try:
                gv_mpd_client = mpd.MPDClient()
                gv_mpd_client.connect("localhost", 6600)
            except:
                log_message('Problem getting mpd client')
                gv_mpd_client = None
                continue

        # Get current MPD status details
        try:
            gv_mpd_client_status = gv_mpd_client.status()
            gv_mpd_client_song = gv_mpd_client.currentsong()
            gv_mpd_playlists = gv_mpd_client.listplaylists()
            gv_mpd_queue = gv_mpd_client.playlistinfo()
            if gv_verbose:
                log_message('MPD Status:\n%s' % (
                    json.dumps(
                        gv_mpd_client_status, 
                        indent = 4)))
                log_message('MPD Current Song:\n%s' % (
                    json.dumps(
                        gv_mpd_client_song, 
                        indent = 4)))
            mpd_last_status = now

        except:
            # reset... and let next loop reconect
            log_message('Problem getting mpd status')
            gv_mpd_client = None
            gv_mpd_client_status = None
            gv_mpd_client_song = None
            gv_mpd_playlists = None
            gv_mpd_queue = None
            continue

        # sanity check on status
        # as it can compe back empty
        if len(gv_mpd_client_status) == 0:
            log_message('Problem getting mpd status')
            continue

        # Start with the current playing/selected file
        mpd_file = None
        if ('file' in gv_mpd_client_song and 
                gv_mpd_client_song['file']):
            mpd_file = gv_mpd_client_song['file']

        # mandatory fields
        mpd_status = gv_mpd_client_status['state']
        mpd_volume = int(gv_mpd_client_status['volume'])
        mpd_repeat = int(gv_mpd_client_status['repeat'])
        mpd_random = int(gv_mpd_client_status['random'])

        # optionals (will depend on given state and stream vs file
        mpd_elapsed = 0
        mpd_duration = 0

        if 'elapsed' in gv_mpd_client_status:
            mpd_elapsed = int(float(gv_mpd_client_status['elapsed']))
        if 'duration' in gv_mpd_client_status:
            mpd_duration = int(float(gv_mpd_client_status['duration']))

        artist = ''
        album = ''
        title = ''
        if 'artist' in gv_mpd_client_song:
            artist = gv_mpd_client_song['artist']
        if 'album' in gv_mpd_client_song:
            album = gv_mpd_client_song['album']
        if 'title' in gv_mpd_client_song:
            title = gv_mpd_client_song['title']

        # MPD Elapsed time and progress
        mpd_elapsed_mins = int(mpd_elapsed / 60)
        mpd_elapsed_secs = mpd_elapsed % 60
        mpd_duration_mins = int(mpd_duration / 60)
        mpd_duration_secs = mpd_duration % 60
        if mpd_duration > 0:
            mpd_progress = int(mpd_elapsed / mpd_duration * 100)
        else:
            mpd_progress = 0

        log_message("Current Track:%s/%s/%s" % (
            artist,
            album,
            title))

        log_message("MPD (%s) vol:%d %d:%02d/%d:%02d [%02d%%]" % (
            mpd_status,
            mpd_volume,
            mpd_elapsed_mins,
            mpd_elapsed_secs,
            mpd_duration_mins,
            mpd_duration_secs,
            mpd_progress))

        # Chromecast URL for media
        if mpd_file:
            cast_url, cast_file_type = mpd_file_to_url(mpd_file)
        else:
            # no file, nothing more to do
            continue

        # Chromecast Status
        if (cast_device):

            # We need an updated status from the Chromecast
            # This can fail sometimes when nothing is really wrong and 
            # then other times when things are wrong :)
            #
            # So we give it a tolerance of 20 consecutive failures
            max_cast_failed_updates = 20
            try:
                cast_device.media_controller.update_status()
                # Reset failed status count
                cast_failed_update_count = 0
                cast_last_status = now
            except:
                cast_failed_update_count += 1
                log_message("Failed to get chromecast status... %d/%d" % (
                    cast_failed_update_count,
                    max_cast_failed_updates))

                if (cast_failed_update_count >= max_cast_failed_updates):
                    log_message("Detected broken controller after %d status failures" % (max_cast_failed_updates))
                    cast_device = None
                    cast_status = 'none'
                    cast_file = 'none'
                    cast_volume = 0
                    cast_failed_update_count = 0
                    continue

            cast_elapsed = int(cast_device.media_controller.status.current_time)

            # Length and progress calculation
            if cast_device.media_controller.status.duration is not None:
                cast_duration = int(cast_device.media_controller.status.duration)
                cast_progress = int(cast_elapsed / cast_duration * 100)
            else:
                cast_duration = 0
                cast_progress = 0

            cast_elapsed_mins = int(cast_elapsed / 60)
            cast_elapsed_secs = cast_elapsed % 60
            cast_duration_mins = int(cast_duration / 60)
            cast_duration_secs = cast_duration % 60

            log_message("%s (%s) vol:%02d %d:%02d/%d:%02d [%02d%%]" % (
                cast_name,
                cast_status,
                cast_volume,
                cast_elapsed_mins,
                cast_elapsed_secs,
                cast_duration_mins,
                cast_duration_secs,
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
                cast_volume = 0
                continue

        # Get cast device when in play state and 
        # no device curently present
        if (mpd_status == 'play' and 
                not cast_device):
            cast_device = get_chromecast(gv_chromecast_name)
            cast_name = gv_chromecast_name

            if not cast_device:
                continue

            # Kill off any current app
            if not cast_device.is_idle:
                log_message("Killing current running cast app")
                cast_device.quit_app()

            while not cast_device.is_idle:
                log_message("Waiting for cast device to get ready...")
                time.sleep(1)

            # Cast state inits
            cast_status = 'none'
            cast_file = 'none'
            cast_volume = 0
            continue


        # MPD -> Chromecast Events
        # Anything that is driven from detecting changes
        # on the MPD side and pushing to the Chromecast

        # Nothing to do if we don't have a cast
        # device handle
        if (not cast_device):
            continue

        # Initial Cast protection for file streaming
        # After an initial cast we pause MPD 
        # only unpausing and re-seeking to 
        # cast_elapsed - 1 when the 
        # chromecast is reporting elapsed time
        # Does not apply for radio streams
        if (not cast_file.startswith('http') and 
                not cast_confirmed and 
                mpd_status == 'pause' and 
                cast_status == 'play'):
            if (cast_elapsed == 0):
                log_message('Initial cast... Waiting for chromecast elapsed time')
            else:
                log_message('Initial cast... elapsed time detected.. Unpausing mpd')
                # sync 1 second behind
                gv_mpd_client.seekcur(cast_elapsed - 1)
                # play (pause 0)
                gv_mpd_client.pause(0)
                cast_confirmed = True
            continue

        # Play a song/stream or next in playlist
        if ((cast_status != 'play' and
            mpd_status == 'play') or
            (mpd_status == 'play' and mpd_file != cast_file)):

            log_message("Casting URL:%s type:%s" % (
                cast_url,
                cast_file_type))

            args = {}
            args['content_type'] = cast_file_type
            args['title'] = title
            args['autoplay'] = True

            albumart_url = get_albumart_url(mpd_file)
            if albumart_url:
                args['thumb'] = albumart_url
                log_message("Albumart URL:%s" % (
                    albumart_url))

            # Let the magic happen
            # Wait for the connection and then issue the 
            # URL to stream
            cast_device.wait()

            if (cast_volume != mpd_volume):
                # Set volume to match local MPD volume
                # avoids sudden volume changes after playback starts when 
                # they sync up
                log_message("Setting Chromecast Volume: %d" % (mpd_volume))
                # Chromecast volume is 0.0 - 1.0 (divide by 100)
                cast_device.set_volume(mpd_volume / 100)

            # Initiate the cast
            cast_device.media_controller.play_media(
                    cast_url, 
                    **args)

            # Note the various specifics of play 
            cast_status = mpd_status
            cast_file = mpd_file
            cast_volume = mpd_volume

            # Pause and seek to start of track
            # only applies to local files
            if (not cast_file.startswith('http')):
                log_message("Pausing MPD (initial cast)")
                gv_mpd_client.pause(1)
                gv_mpd_client.seekcur(0)
                cast_confirmed = False

            # no more to do until next loop
            continue
  
        # Volume change only while playing
        if (cast_status == 'play' and 
                cast_volume != mpd_volume):

            log_message("Setting Chromecast Volume: %d" % (mpd_volume))
            # Chromecast volume is 0.0 - 1.0 (divide by 100)
            cast_device.set_volume(mpd_volume / 100)
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
            cast_volume = 0
            continue  

        # Detect a skip on MPD and issue a seek request on the 
        # chromecast.
        #
        # Make sure the cast is confirmed and only perform the
        # seek if there is a difference of min 10 seconds
        # That prevents mis-fire if the two elapsed times are 
        # just out of sync versus an actual mpd seek being performed
        if (not cast_file.startswith('http') and 
                mpd_status == 'play' and 
                cast_status == 'play' and 
                cast_confirmed and
                cast_elapsed > 0 and
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
        # behind the chromecast elapsed time.
        if (not cast_file.startswith('http') and
                mpd_status == 'play' and 
                cast_elapsed > 0 and 
                cast_elapsed % 10 == 0 and
                (mpd_elapsed >= cast_elapsed or
                    mpd_elapsed < cast_elapsed - 1)):
                log_message(
                        "Sync Chromecast elapsed %d secs to MPD" % (
                            cast_elapsed))

                # Value for seek is 1 second behind
                gv_mpd_client.seekcur(cast_elapsed - 1)

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
determine_platform_variant()

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
        log_message("Detected %d dead threads... exiting" % (dead_threads))
        sys.exit(-1);

    # MPD/Chromecast deadlock
    # The MPD loop runs more or less on a 
    # 1-second interval. It will delay and 
    # potentially lock-up if either an MPD or pychromecast
    # call goes bad. This will detect 60 seconds deadlock and exit
    now = int(time.time())
    if (gv_mpd_agent_timestamp > 0 and 
            now - gv_mpd_agent_timestamp >= 60):
        log_message("Detected deadlocked MPD agent... exiting")
        sys.exit(-1);

    time.sleep(5)

