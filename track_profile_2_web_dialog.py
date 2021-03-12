# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TrackProfile2webDialog
                                 A QGIS plugin
 Leaflet interactive web profiles.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2019-05-24
        git sha              : $Format:%H$
        copyright            : (C) 2019 by Matteo Ghetta
        email                : matteo.ghetta@faunalia.eu
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from collections import OrderedDict
from shutil import copyfile
import json
import tempfile
import webbrowser
import re

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWebKit import QWebSettings
from qgis.PyQt.QtCore import (
    QUrl,
    QFileInfo
)

import processing

from qgis.PyQt.QtGui import(
    QColor
)
from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QSizePolicy,
    QGridLayout,
    QPushButton
)

from qgis.core import (
    QgsMapLayerProxyModel,
    Qgis,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsCoordinateTransform,
    QgsVectorFileWriter
)

from qgis.gui import(
    QgsMessageBar
)

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'track_profile_2_web_dialog_base.ui'))


class TrackProfile2webDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(TrackProfile2webDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)


        # filter only QgsVector Line Layers
        self.layer_combo.setFilters(QgsMapLayerProxyModel.LineLayer)

        # get QWebView settings and add options for optimization
        mapview_settings = self.mapview.settings()
        mapview_settings.setAttribute(QWebSettings.WebGLEnabled, True)
        mapview_settings.setAttribute(QWebSettings.DeveloperExtrasEnabled, True)
        mapview_settings.setAttribute(QWebSettings.Accelerated2dCanvasEnabled, True)

        self.tile_maps = OrderedDict([
            ('OpenTopoMap', {
                'tile': 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
                'attribution': 'Map data: &copy; <a href="http://www.openstreetmap.org/copyright">OpenTopoMap</a>, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)'
                }
            ),
            ('OpenStreetMap', {
                'tile': 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                'attribution': 'Map data: &copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://openstreetmap.org">OpenStreetMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)'
                }
            ),
            ('WikimediaMap', {
                'tile': 'https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png',
                'attribution': 'Map data: &copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://openstreetmap.org">OpenStreetMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)'
                }
            ),
            ('Google', {
                'tile': 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
                'attribution': ''
                }
            ),
            ('ESRI Satellite Map', {
                'tile': 'http://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                'attribution': '&copy; <a href="http://www.esri.com/">Esri</a>'
                }
            )
        ])
        self.basemap_combo.clear()
        for k, v in self.tile_maps.items():
            self.basemap_combo.addItem(k, v)

        # list of attached profile positions as OrderedDict
        self.profile_position = OrderedDict([
            (self.tr('Top Right'), 'topright'),
            (self.tr('Top Left'), 'topleft'),
            (self.tr('Bottom Right'), 'bottomright'),
            (self.tr('Bottom Left'), 'bottomleft')
        ])
        self.profile_combo.clear()
        for k, v in self.profile_position.items():
            self.profile_combo.addItem(k, v)

        # set default colors
        self.profile_color.setColor(QColor('#d45f5f'))
        self.marker_color.setColor(QColor('#ffb800'))
        self.line_color.setColor(QColor('#ff0000'))

        # create instance of QgsMessageBar (used later)
        self.bar = QgsMessageBar()
        self.bar.setSizePolicy( QSizePolicy.Minimum, QSizePolicy.Fixed )
        self.setLayout(QGridLayout())
        self.layout().addWidget(self.bar, 1, 0, 1, 1)

        # connect buttons to specific functions
        self.update_btn.clicked.connect(self.changeMap)
        self.browser_btn.clicked.connect(self.openBrowser)
        self.export_btn.clicked.connect(self.saveAsHtml)
        self.export_geojson_btn.clicked.connect(self.saveAsHtmlGeojson)

        # connect to function to disable profile position buttons
        self.detach_check.toggled.connect(self.refreshState)
        self.update_btn.clicked.connect(self.refreshState2)
        # set profile postion buttons as disabled
        self.label_position.setEnabled(False)
        self.profile_combo.setEnabled(False)
        self.auto_hide.setEnabled(False)


    def refreshState(self):
        '''
        When Detached profile checkbox is checked enable buttons accordingly
        '''
        if not self.detach_check.isChecked():
            self.label_position.setEnabled(True)
            self.profile_combo.setEnabled(True)
            self.auto_hide.setEnabled(True)
        else:
            self.label_position.setEnabled(False)
            self.profile_combo.setEnabled(False)
            self.auto_hide.setEnabled(False)

    def refreshState2(self):
        '''
        Prevent to have clickable button if the Update Map is not clicked
        at least once
        '''

        self.browser_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.export_geojson_btn.setEnabled(True)

    def changeMap(self):
        '''
        Main function of the plugin. Draws the map with the Line layer and
        tweaks all the options chosen
        '''

        # reference of the main QgsVectorLayer
        self.vlayer = self.layer_combo.currentLayer()

        # Check if the layer as Z values, if not stop the algorithm
        if not QgsWkbTypes.hasZ(self.vlayer.wkbType()):

            def open_drape():
                '''
                function to open Processing algorithm dialog, used later
                '''
                processing.execAlgorithmDialog('native:setzfromraster')

            # create the widget with the message that will be shown
            widget = self.bar.createMessage(self.tr("The selected layer has not Z values. Add them using the Drape algorithm of the Processing toolbox"))
            # create the button to put into the messageBar
            button = QPushButton(widget)
            button.setText(self.tr('Open Drape Algorithm?'))
            # connect the button to the function to open the drape algorithm
            button.pressed.connect(open_drape)
            # add the button to the messageBar widget
            widget.layout().addWidget(button)
            # create the messageBar with the message and the button
            self.bar.pushWidget(widget, Qgis.Critical, duration=10)
            return

        # dictionary of all the js functions, will be json dumped after
        self.opts = {
            "map": {
                "mapTypeId": 'terrain',
                "center": [41.4583, 12.7059],
                "zoom": 5,
            #   "markerZoomAnimation": False,
            #   "zoomControl": False,
            },
            "zoomControl": {
                "position": 'topleft',
            },
            "elevationControl": {
                "data": None, #sample data placeholder
                "theme": 'custom-theme',
                "elevationDiv": '#elevation-div',
                "detached": True,
                "position": 'topright',
                "autohide": False,
                "collapsed": True,
                "position": 'topright',
                "followMarker": False,
                "autofitBounds": True,
                "imperial": False,
                "reverseCoords": False,
                "acceleration": False,
                "slope": False,
                "speed": False,
                "time": False,
                "distance": True,
                "altitude": True,
                "summary": 'multiline',
                "ruler": True,
                "legend": True,
                "almostOver": True,
                "distanceMarkers": False,
                "preferCanvas": True
                },
            "layersControl": {
              "options": {
                "collapsed": True,
              },
            },
            "otmLayer": {
              "url" : None,
              "options": {
                "attribution": '',
              }
            },
        }


        data = '''{{"name":"{layer}", "type":"FeatureCollection","features": ['''.format(layer=self.vlayer.name())

        # set the QgsCoordinateTransform context used in to reproject the layer if needed
        crsSrc = self.vlayer.crs()
        crsDest = QgsCoordinateReferenceSystem(4326)
        xform = QgsCoordinateTransform(crsSrc, crsDest, QgsProject.instance())

        # start the loop to write the data formatted in the correct way
        for i in self.vlayer.getFeatures():

            geometry = i.geometry()

            # transform the geometry to 4326 if needed
            if not self.vlayer.crs().authid() == 'EPSG:4326':
                geometry.transform(xform)
                i.setGeometry(geometry)

            data += '{ "type": "Feature", "properties": { }, "geometry": { "type": "LineString", "coordinates": [ '

            # check and tweak the layer if it is MultiPart and has Multiparts
            if geometry.isMultipart() and i.geometry().constGet().partCount() > 1:

                g = geometry.asGeometryCollection()

                for geom in g:
                    for part in geom.constParts():
                        for coord in part:
                            data += ' [{}, {}, {}],'.format(coord.x(), coord.y(), coord.z())

            # if the layer is not MultiPart continue
            else:
                g = geometry.constParts()

                for part in g:
                    for coord in part.vertices():
                        data += ' [{}, {}, {}],'.format(coord.x(), coord.y(), coord.z())

            data = data[:-1]

            data += '] } },'

        data = data[:-1]
        data += ''']}'''

        # set the user options to the dictionary
        self.opts["elevationControl"]["data"] = data
        self.opts["elevationControl"]["detached"] = self.detach_check.isChecked()
        self.opts["elevationControl"]["followMarker"] = self.follow_track.isChecked()
        self.opts["elevationControl"]["position"] = self.profile_position[self.profile_combo.currentText()]
        self.opts["elevationControl"]["collapsed"] = self.profile_collapse.isChecked()
        self.opts["elevationControl"]["autohide"] = self.auto_hide.isChecked()
        self.opts["layersControl"]["options"]["collapsed"] = self.layers_collapse.isChecked()
        try:
            self.opts["otmLayer"]["url"] = self.tile_maps[self.basemap_combo.currentText()]['tile']
            self.opts["otmLayer"]["options"]["attribution"] = self.tile_maps[self.basemap_combo.currentText()]['attribution']
        except KeyError as e:
            self.opts["otmLayer"]["url"] = self.basemap_combo.currentText()

        # get the path of the template.html file used to write the final file
        self.fin = os.path.join(os.path.dirname(__file__), 'template.html')
        # get the path (from tempfolder) where to write the final result
        self.fout = os.path.join(
            tempfile.gettempdir(), 'template.html')

        # read the content of the input template.html file
        with open(self.fin, 'r') as fi:
            self.lines = fi.readlines()

        for i, j in enumerate(self.lines):
            if '{ py_opts }' in j: # search for '{{ py_opts }}' placeholder
                self.dataidx = i
            if '{ area_fill_color }' in j: # search for '{ area_fill_color }' placeholder
                area_fill_idx = i
            if '{ area_stroke_width }' in j: # search for '{ area_stroke_width }' placeholder
                area_stroke_width_idx = i
            if '{ marker_color }' in j: # search for '{ marker_color }' placeholder
                marker_color_idx = i
            if '{ line_color }' in j: # search for '{ line_color }' placeholder
                line_color_idx = i
            if '{ line_opacity }' in j: # search for '{ line_opacity }' placeholder
                line_opacity_idx = i

        # dump the opts dictionary as json
        json_opts = json.dumps(self.opts)

        # replace all the user options to the correct line indexes
        self.lines[self.dataidx] = '  var opts = {} ;'.format(json_opts)
        self.lines[area_fill_idx] = self.lines[area_fill_idx].replace('{ area_fill_color }', self.profile_color.color().name())
        self.lines[area_stroke_width_idx] = self.lines[area_stroke_width_idx].replace('{ area_stroke_width }', str(self.profile_stroke_width.value()))
        self.lines[marker_color_idx] = self.lines[marker_color_idx].replace('{ marker_color }', self.marker_color.color().name())
        self.lines[line_color_idx] = self.lines[line_color_idx].replace('{ line_color }', self.line_color.color().name())
        self.lines[line_opacity_idx] = self.lines[line_opacity_idx].replace('{ line_opacity }', str(self.marker_opacity.value()))

        # write the final file
        with open(self.fout, 'w') as fo:
            fo.writelines(self.lines)

        # get the path of the output file as QUrl
        leaftemplate_new = QUrl.fromLocalFile(self.fout)
        # load the QUrl into the QWebView
        self.mapview.load(leaftemplate_new)


    def openBrowser(self):
        '''
        Open the html in Browser
        '''

        webbrowser.open(self.fout)


    def saveAsHtml(self):
        '''
        Open a dialog and let the user choose the location to write the file.
        The file is a single html with the injected data as geojson.
        '''

        dial, _ = QFileDialog.getSaveFileName(None, self.tr("Save Elevation file"), "", "*.html")
        elevation_file = QFileInfo(dial).absoluteFilePath()
        elevation_file += '.html'

        try:
            copyfile(self.fout, elevation_file)
            self.bar.pushMessage(self.tr("Elevation file succesfully saved"), "", level=Qgis.Info, duration=3)
        except:
            self.bar.pushMessage(self.tr("Something went wrong. Try again."), "", level=Qgis.Critical, duration=3)

    def saveAsHtmlGeojson(self):
        '''
        Open a directory dialog and le the user choose the location where to
        write the html and the geojson file.
        '''

        export_name = re.sub(r'\s+','-', self.vlayer.name())

        dir_path = QFileDialog.getExistingDirectory(None, self.tr("Select Directory"))
        html_name = os.path.join(dir_path, '{}.html'.format(export_name))
        # remove all spaces from name
        gjson_name = os.path.join(dir_path, '{}.geojson'.format(export_name))

        output = QgsVectorFileWriter.writeAsVectorFormat(
            layer=self.vlayer,
            fileEncoding='UTF-8',
            fileName=gjson_name,
            driverName='GeoJSON')

        # change the raw geojson string with the relative file path
        self.opts["elevationControl"]["data"] = os.path.basename(gjson_name)

        geojson_opts = json.dumps(self.opts)
        self.lines[self.dataidx] = '  var opts = {} ;'.format(geojson_opts)

        # write the final file
        try:
            with open(html_name, 'w') as fog:
                fog.writelines(self.lines)
            self.bar.pushMessage(self.tr("Elevation file succesfully saved"), "", level=Qgis.Info, duration=3)
        except:
            self.bar.pushMessage(self.tr("Something went wrong. Try again."), "", level=Qgis.Critical, duration=3)
