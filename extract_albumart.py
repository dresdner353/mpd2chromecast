#!/usr/bin/env python3
# coding=utf-8

import argparse
import os
import json
import mutagen
import sys

# main
parser = argparse.ArgumentParser(
        description='Extract Albumart')

parser.add_argument('--mpd_dir', 
                    help = 'MPD Music Directory', 
                    default = '/var/lib/mpd/music',
                    required = False)

args = vars(parser.parse_args())
mpd_dir = args['mpd_dir']

art_names = [
        'cover.png',
        'cover.jpg',
        'cover.tiff',
        'cover.bmp',
        'cover.gif',
        ]

music_file_exts = [
        'flac',
        'mp3',
        'mp4',
        'm4a',
        ]

total_created = 0
total_failures = 0
total_existing = 0
total_dirs_scanned = 0

for root, dirs, files in os.walk(
        mpd_dir,
        followlinks = True):
    total_dirs_scanned += 1
    print('Scanned %d directories        ' % (total_dirs_scanned), end = '\r')
    # test for cover.XXX in directory
    cover_exists = False
    for name in art_names:
        cover_file = os.path.join(root, name)
        if os.path.exists(cover_file):
            cover_exists = True
            break

    if cover_exists:
        total_existing += 1
        continue

    # Scan files that match music extension and 
    # try to source cover from first one found 
    source_file = None
    for file in files:
        for ext in music_file_exts:
            if file.endswith(ext):
                 source_file = os.path.join(root, file)
                 break

        if source_file:
            # skip any further file checks
            break

    if source_file:
        print('Extracting albumart from %s' % (source_file))
        # Analyse file with mutagen and try to extract albumart
        mrec = mutagen.File(source_file)

        if type(mrec) == mutagen.flac.FLAC:
            if (len(mrec.pictures) > 0):
                albumart_mime = mrec.pictures[0].mime
                albumart_data = mrec.pictures[0].data

        elif type(mrec) == mutagen.mp3.MP3:
            for tag in mrec.tags.keys():
                if tag.startswith('APIC'):
                    albumart_mime = mrec.tags[tag].mime
                    albumart_data = mrec.tags[tag].data
                    break

        elif type(mrec) == mutagen.mp4.MP4:
            if 'covr' in mrec.tags:
                albumart_data = mrec.tags['covr'][0]
                if mrec.tags['covr'][0].imageformat == 13:
                    albumart_mime = 'image/jpg'
                else:
                    albumart_mime = 'image/png'

        if albumart_data:
            # Write detected embedded albumart to a file
            albumart_ext = albumart_mime.replace('image/', '')
            if albumart_ext == 'jpeg':
                albumart_ext = 'jpg'
            albumart_filename = 'cover.%s' % (albumart_ext)
            albumart_path = os.path.join(root, albumart_filename)
            try:
                aa_file = open(albumart_path, 'wb')
                aa_file.write(albumart_data)
                aa_file.close()
                total_created += 1
                print('Created %s' % (albumart_path))
            except:
                print('Failed to create %s' % (albumart_path))
                total_failures += 1


print('\n\nComplete')
print('Scanned %d directories' % (total_dirs_scanned))
print('Created %d covers' % (total_created))
print('Failed to create %d covers' % (total_failures))
print('Found %d existing covers' % (total_existing))
