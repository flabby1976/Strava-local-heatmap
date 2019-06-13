# Copyright (c) 2018 Remi Salmon
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# imports
import os
import glob
import time
import re
import argparse
import urllib

import numpy as np
import matplotlib.pyplot as plt

from scipy.ndimage import gaussian_filter

import xml.etree.cElementTree as ET

# functions
def deg2num(lat_deg, lon_deg, zoom): # return OSM x,y tile ID from lat,lon in degrees (from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames)
  lat_rad = np.radians(lat_deg)
  n = 2.0 ** zoom
  xtile = int((lon_deg + 180.0) / 360.0 * n)
  ytile = int((1.0 - np.log(np.tan(lat_rad) + (1 / np.cos(lat_rad))) / np.pi) / 2.0 * n)
  return(xtile, ytile)

def num2deg(xtile, ytile, zoom): # return x,y coordinates in tile from lat,lon in degrees (from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames)
  n = 2.0 ** zoom
  lon_deg = xtile / n * 360.0 - 180.0
  lat_rad = np.arctan(np.sinh(np.pi * (1 - 2 * ytile / n)))
  lat_deg = np.degrees(lat_rad)
  return (lat_deg, lon_deg)

def deg2xy(lat_deg, lon_deg, zoom): # return x,y coordinates in tile from lat,lon in degrees
    lat_rad = np.radians(lat_deg)
    n = 2.0 ** zoom
    x = (lon_deg + 180.0) / 360.0 * n
    y = (1.0 - np.log(np.tan(lat_rad) + (1 / np.cos(lat_rad))) / np.pi) / 2.0 * n
    return(x, y)

def main(args): # main script
    # parameters
    gpx_dir = args.dir # string
    gpx_filter = args.filter # string
    gpx_year = args.year # string
    lat_north_bound, lon_west_bound, lat_south_bound, lon_east_bound = args.bound # int
    picture_output = args.filename # string
    max_nb_tiles = args.maxtiles # int
    sigma_pixels = args.sigma # int
    use_csv = args.csv # bool
    use_cumululative_distribution = not args.nocdist # bool

    # constants
    tile_size = [256, 256] # OSM tile size (default)
    zoom = 19 # OSM max zoom level (default)
    colormap = 'winter' # matplotlib color map (from https://matplotlib.org/examples/color/colormaps_reference.html)

    # find GPX files
    gpx_files = glob.glob(gpx_dir+'/'+gpx_filter)

    if not gpx_files:
        print('ERROR: no GPX files in '+gpx_dir)
        quit()

    # read GPX files
    lat_lon_data = [] # initialize latitude, longitude list

    for i in range(len(gpx_files)):
        print('reading GPX file '+str(i+1)+'/'+str(len(gpx_files))+'...'+gpx_files[i])

        tree=ET.ElementTree(file=gpx_files[i])
        root=tree.getroot()

        tracks = root.findall('{http://www.topografix.com/GPX/1/1}trk')
        for trk in tracks:
            trksegs = trk.findall('{http://www.topografix.com/GPX/1/1}trkseg')
            for trkseg in trksegs:
                trkpoints = trkseg.findall('{http://www.topografix.com/GPX/1/1}trkpt')
                for trkpt in trkpoints:
                    coords = trkpt.attrib
                    dt = trkpt.find('{http://www.topografix.com/GPX/1/1}time').text
                    if gpx_year in (dt, 'all'):
                        lat = float (coords['lat'])
                        lon = float (coords['lon'])
                        lat_lon_data.append([lat, lon])

    # find TCX files
    gpx_files = glob.glob(gpx_dir+'/*.tcx')

    for i in range(len(gpx_files)):
        print('reading TCX file '+str(i+1)+'/'+str(len(gpx_files))+'...'+gpx_files[i])

        with open(gpx_files[i], 'r') as f:
            output = f.read()
        root=ET.fromstring(output.lstrip())

        top = root.find('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Activities')
        activities = top.findall('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Activity')
        for activity in activities:
            laps = activity.findall('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Lap')
            for lap in laps:
                tracks = lap.findall('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Track')
                for track in tracks:
                    trackpoints = track.findall('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Trackpoint')
                    for trackpoint in trackpoints:
                        coords = trackpoint.attrib
                        dt = trackpoint.find('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Time').text
                        if gpx_year in (dt, 'all'):
                            position = trackpoint.find(
                                '{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Position')
                            if position:
                                lat = float(position.find('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}LatitudeDegrees').text)
                                lon = float(position.find('{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}LongitudeDegrees').text)
                                lat_lon_data.append([lat, lon])

    if not lat_lon_data:
        print('ERROR: no matching data found')
        quit()

    print('processing GPX data...')

    lat_lon_data = np.array(lat_lon_data) # convert list to NumPy array

    print(lat_lon_data.size)

    # crop data to bounding box
    lat_lon_data = lat_lon_data[np.logical_and(lat_lon_data[:, 0] > lat_south_bound, lat_lon_data[:, 0] < lat_north_bound), :]
    lat_lon_data = lat_lon_data[np.logical_and(lat_lon_data[:, 1] > lon_west_bound, lat_lon_data[:, 1] < lon_east_bound), :]

    # find good zoom level to match max_nb_tiles
    xy_tiles_minmax = np.zeros((4, 2), dtype = int) # x,y tile coordinates of bounding box

    lat_min = lat_lon_data[:, 0].min()
    lat_max = lat_lon_data[:, 0].max()
    lon_min = lat_lon_data[:, 1].min()
    lon_max = lat_lon_data[:, 1].max()

    while True:
        xy_tiles_minmax[0, :] = deg2num(lat_min, lon_min, zoom)
        xy_tiles_minmax[1, :] = deg2num(lat_min, lon_max, zoom)
        xy_tiles_minmax[2, :] = deg2num(lat_max, lon_min, zoom)
        xy_tiles_minmax[3, :] = deg2num(lat_max, lon_max, zoom)

        x_tile_min = xy_tiles_minmax[:, 0].min()
        x_tile_max = xy_tiles_minmax[:, 0].max()
        y_tile_min = xy_tiles_minmax[:, 1].min()
        y_tile_max = xy_tiles_minmax[:, 1].max()

        if (x_tile_max-x_tile_min+1) > max_nb_tiles or (y_tile_max-y_tile_min+1) > max_nb_tiles:
            zoom = zoom-1 # decrease zoom level if number of tiles used is too high
        else:
            break

    tile_count = (x_tile_max-x_tile_min+1)*(y_tile_max-y_tile_min+1) # total number of tiles

    print(lat_max, lat_min, lon_max, lon_min )

    # download tiles
    if not os.path.exists('tiles'):
        os.mkdir('tiles')

    print('downloading tiles if required...')
    i = 0
    for x in range(x_tile_min, x_tile_max+1):
        for y in range(y_tile_min, y_tile_max+1):
            tile_url = 'https://maps.wikimedia.org/osm-intl/'+str(zoom)+'/'+str(x)+'/'+str(y)+'.png' # (from https://wiki.openstreetmap.org/wiki/Tile_servers)
            tile_filename = 'tiles/tile_'+str(zoom)+'_'+str(x)+'_'+str(y)+'.png'

            i = i + 1
            if not glob.glob(tile_filename): # check if tile already downloaded
                print('downloading tile '+str(i)+'/'+str(tile_count)+'...')

                try:
                    response = urllib.request.urlopen(tile_url)
                except urllib.error.URLError as e: # catches both URLError and HTTPError
                    print('ERROR: cannot download tile from server')
                    print(e.reason)
                    quit()
                else:
                    with open(tile_filename, 'wb') as file:
                        file.write(response.read())
                    time.sleep(0.1)

    print('creating map background...')

    # create supertile
    supertile_size = [(y_tile_max-y_tile_min+1)*tile_size[0], (x_tile_max-x_tile_min+1)*tile_size[1], 3]

    supertile = np.zeros(supertile_size)

    for x in range(x_tile_min, x_tile_max+1):
        for y in range(y_tile_min, y_tile_max+1):
            tile_filename = 'tiles/tile_'+str(zoom)+'_'+str(x)+'_'+str(y)+'.png'

            tile = plt.imread(tile_filename) # float data type ([0,1])

            i = y-y_tile_min
            j = x-x_tile_min

            supertile[i*tile_size[0]:i*tile_size[0]+tile_size[0], j*tile_size[1]:j*tile_size[1]+tile_size[1], :] = tile # fill supertile with tile image

    # convert supertile to grayscale and invert colors
    supertile = 0.2126*supertile[:, :, 0]+0.7152*supertile[:, :, 1]+0.0722*supertile[:, :, 2] # convert to 1 channel grayscale image
    supertile = 1-supertile # invert colors
    supertile = np.dstack((supertile, supertile, supertile)) # convert back to 3 channels image

    # fill trackpoints data
    data = np.zeros(supertile_size[0:2])

    w_pixels = int(sigma_pixels) # add w_pixels (= Gaussian kernel sigma) pixels of padding around the trackpoints for better visualization

    print('creating heatmap...')
    for k in range(len(lat_lon_data)):
        (x, y) = deg2xy(lat_lon_data[k, 0], lat_lon_data[k, 1], zoom)

        i = int(np.round((y-y_tile_min)*tile_size[0]))
        j = int(np.round((x-x_tile_min)*tile_size[1]))

        data[i-w_pixels:i+w_pixels+1, j-w_pixels:j+w_pixels+1] = data[i-w_pixels:i+w_pixels+1, j-w_pixels:j+w_pixels+1] + 1 # ensure pixels are centered on the trackpoint

    # threshold trackpoints accumulation to avoid large local maxima
    if use_cumululative_distribution:
        pixel_res = 156543.03*np.cos(np.radians(lat_lon_data[:, 0].mean()))/(2**zoom) # pixel resolution (from https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames)

        m = (1.0/5.0)*pixel_res*len(gpx_files) # trackpoints max accumulation per pixel = (1/5) trackpoints/meters * (pixel_res) meters/pixels per (1) activity (Strava records trackpoints every 5 meters in average for cycling activites)
    else:
        m = 1.0

    print('thresholding data...')
    data[data > m] = m # threshold data to maximum accumulation of trackpoints

    print('filtering data...')
    # kernel density estimation = convolution with Gaussian kernel
    data = gaussian_filter(data, sigma_pixels)

    # normalize data to [0,1]
    data = (data-data.min())/(data.max()-data.min())

    # colorize data
    cmap = plt.get_cmap(colormap)

    data_color = cmap(data)
    data_color[(data_color == cmap(0)).all(2)] = [0.0, 0.0, 0.0, 1.0] # remove background color
    data_color = data_color[:, :, 0:3] # remove alpha channel

    # create color overlay
    supertile_overlay = np.zeros(supertile_size)

    for c in range(3):
        supertile_overlay[:, :, c] = (1-data_color[:, :, c])*supertile[:, :, c]+data_color[:, :, c] # fill color overlay

    # save image
    if not os.path.splitext(picture_output)[1] == '.png': # make sure we use PNG
        picture_output = os.path.splitext(picture_output)[0]+'.png'

    print('saving '+picture_output+'...')

    plt.imsave(picture_output, supertile_overlay)

    # save csv file
    if use_csv:
        csv_output = picture_output[:-4]+'.csv'

        print('saving '+csv_output+'...')

        with open(csv_output, 'w') as file:
            file.write('lat,lon,intensity\n')

            for i in range(data.shape[0]):
                for j in range(data.shape[1]):
                    if data[i, j] > 0.1:
                        x = x_tile_min+j/tile_size[1]
                        y = y_tile_min+i/tile_size[0]

                        (lat, lon) = num2deg(x, y, zoom)

                        file.write(str(lat)+','+str(lon)+','+str(data[i, j])+'\n')

    print('done')

if __name__ == '__main__':
    # command line parameters
    parser = argparse.ArgumentParser(description = 'Generate a local heatmap from Strava GPX files', epilog = 'Report issues to https://github.com/remisalmon/strava-local-heatmap')
    parser.add_argument('--gpx-dir', dest = 'dir', default = 'gpx', help = 'directory containing the GPX files (default: gpx)')
    parser.add_argument('--gpx-filter', dest = 'filter', default = '*.gpx', help = 'regex filter for the GPX files (default: *.gpx)')
    parser.add_argument('--gpx-year', dest = 'year', default = 'all', help = 'year for which to read the GPX files (default: all)')
    parser.add_argument('--gpx-bound', dest = 'bound', type = float, nargs = 4, default = [+90, -180, -90, +180], help = 'heatmap bounding box as lat_north_bound, lon_west_bound, lat_south_bound, lon_east_bound (default: 90 -180 -90 180)')
    parser.add_argument('--output', dest = 'filename', default = 'heatmap.png', help = 'heatmap file name (default: heatmap.png)')
    parser.add_argument('--max-tiles', dest = 'maxtiles', type = int, default = 3, help = 'heatmap maximum dimension  in tiles, 1 tile = 256 pixels (default: 3)')
    parser.add_argument('--sigma-pixels', dest = 'sigma', type = int, default = 1, help = 'heatmap Gaussian kernel half-bandwith in pixels (default: 1)')
    parser.add_argument('--csv-output', dest = 'csv', action = 'store_true', help = 'enable CSV output of the heatmap in addition to the PNG image (lat,lon,intensity)')
    parser.add_argument('--no-cdist', dest = 'nocdist', action = 'store_true', help = 'disable cumulative distribution of trackpoints (converts to uniform distribution)')
    args = parser.parse_args()

    # main script
    main(args)
