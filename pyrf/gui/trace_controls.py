from collections import namedtuple

from PySide import QtGui, QtCore
from pyrf.gui import labels
from pyrf.gui import colors
from pyrf.gui.util import hide_layout

import numpy as np

PLOT_YMIN = -140
PLOT_YMAX = 0

REMOVE_BUTTON_WIDTH = 10

class TraceWidgets(namedtuple('TraceWidgets', """
    icon
    label
    draw
    hold
    add
    remove
    add_marker
    """)):
    """
    :param icon: color icon
    :param label: trace name label
    :param draw: draw combobox, including 'Live', 'Max', 'Min' options
    :param hold: hold checkbox
    :param add: "+ trace" button
    :param remove: "- trace" button
    :param add_marker: "+ marker" button for adding a marker to this trace
    """
    __slots__ = []

class MarkerWidgets(namedtuple('MarkerWidgets', """
    marker
    center
    peak_left
    peak
    peak_right
    remove
    """)):
    """
    :param marker: marker name radio button assigned to button_group
    :param center: "center" button
    :param peak_left: "peak left" button
    :param peak: "peak" button
    :param peak_right: "peak right" button
    :param remove: "- marker" button
    """
    __slots = []

class TraceControls(QtGui.QGroupBox):
    """
    A widget based from the Qt QGroupBox widget with a layout containing widgets that
    can be used to control the FFT plot's traces
    :param name: The name of the groupBox
    """
    def __init__(self, controller, plot, name="Trace Control"):
        super(TraceControls, self).__init__()

        self.controller = controller
        controller.state_change.connect(self.state_changed)
        controller.capture_receive.connect(self.capture_received)
        self._plot = plot
        self.setTitle(name)
        self._marker_trace = None
        self.marker_selected = 0

        self.setLayout(QtGui.QGridLayout())
        self._create_controls()
        self._build_layout()

    def _create_controls(self):
        self._traces = []
        for num in range(len(colors.TRACE_COLORS)):
            self._traces.append(self._create_trace_widgets(num))

        self._markers = []
        self._marker_group = QtGui.QButtonGroup()
        for num in (0, 1):
            self._markers.append(self._create_marker_widgets(num,
                self._marker_group))

    def _create_trace_widgets(self, num):
        """
        :param num: index of this set of trace controls from 0 - 2

        :returns: a TraceWidgets namedtuple
        """
        r, g, b = colors.TRACE_COLORS[num]
        color = QtGui.QColor()
        color.setRgb(r, g, b)
        pixmap = QtGui.QPixmap(22, 6)
        pixmap.fill(color)
        #icon = QtGui.QIcon(pixmap)
        icon = QtGui.QLabel()
        icon.setPixmap(pixmap)

        label = QtGui.QLabel("Trace %d:" % (num + 1))

        draw = QtGui.QComboBox()
        draw.setToolTip("Select data source")
        for i, val in enumerate(['Live', 'Max', 'Min']):
            draw.addItem(val)
        draw.setCurrentIndex(num)  # default draw 0: Live, 1: Max, 2: Min
        def draw_changed(index):
            [self.trace_write, self.max_hold, self.min_hold][index](num)
        draw.currentIndexChanged.connect(draw_changed)

        hold = QtGui.QCheckBox("Pause")
        hold.setToolTip("Pause trace updating")
        def hold_clicked():
            self._store_trace(num, hold.isChecked())
        hold.clicked.connect(hold_clicked)

        add_trace = QtGui.QPushButton("+ Trace")
        add_trace.setToolTip("Enable this trace")
        def add_trace_clicked():
            draw_changed(draw.currentIndex())
            if hold.isChecked():  # force hold off
                hold.click()
            self._build_layout()
        add_trace.clicked.connect(add_trace_clicked)

        remove_trace = QtGui.QPushButton("-")
        remove_trace.setMinimumWidth(REMOVE_BUTTON_WIDTH)
        remove_trace.setToolTip("Disable this trace")
        def remove_trace_clicked():
            self.blank_trace(num)
            self._build_layout()
        remove_trace.clicked.connect(remove_trace_clicked)

        add_marker = QtGui.QPushButton("+ Marker")
        add_marker.setToolTip("Add a marker to this trace")
        def add_marker_clicked():
            m = 0 if not self._plot.markers[0].enabled else 1
            self._plot.markers[m].enable(self._plot)
            self._plot.markers[m].trace_index = num
            if not self._markers[m].marker.isChecked():
                self._markers[m].marker.click()  # select markers when adding
            self._build_layout()
        add_marker.clicked.connect(add_marker_clicked)

        return TraceWidgets(icon, label, draw, hold, add_trace, remove_trace,
            add_marker)

    def _create_marker_widgets(self, num, button_group):
        """
        :param num: index of this marker (currently 0 or 1)
        :param button_group: QButtonGroup for the marker radio buttons

        :returns: a MarkerWidgets namedtuple

        """
        radio = QtGui.QRadioButton("Marker %d:" % (num + 1))
        button_group.addButton(radio)
        def marker_select():
            self.marker_selected = num
        radio.clicked.connect(marker_select)

        center = QtGui.QPushButton("Center")
        center.setToolTip("Center the frequency on this marker")
        def center_clicked():
            marker = self._plot.markers[num]
            if marker.enabled:
                self.controller.apply_settings(center=
                    self.xdata[marker.data_index])
                marker.data_index = len(self.pow_data)/2
        center.clicked.connect(center_clicked)

        peak_left = QtGui.QPushButton("Peak Left")
        peak_left.setToolTip("Find peak left of the marker")
        def peak_left_clicked():
            self._find_left_peak(num)
        peak_left.clicked.connect(peak_left_clicked)

        peak = QtGui.QPushButton("Peak")
        peak.setToolTip("Find the peak of the selected spectrum")
        def peak_clicked():
            self._find_peak(num)
        peak.clicked.connect(peak_clicked)

        peak_right = QtGui.QPushButton("Peak Right")
        peak_right.setToolTip("Find peak right of the marker")
        def peak_right_clicked():
            self._find_right_peak(num)
        peak_right.clicked.connect(peak_right_clicked)

        remove_marker = QtGui.QPushButton("-")
        remove_marker.setMinimumWidth(REMOVE_BUTTON_WIDTH)
        remove_marker.setToolTip("Remove this marker")
        def remove_marker_clicked():
            self._plot.markers[num].disable(self._plot)
            self._build_layout()
        remove_marker.clicked.connect(remove_marker_clicked)

        return MarkerWidgets(radio, center, peak_left, peak, peak_right,
            remove_marker)

    def _build_layout(self):
        """
        rebuild grid layout based on marker and trace states
        """
        grid = self.layout()
        hide_layout(grid)
        def show(widget, y, x, h, w):
            grid.addWidget(widget, y, x, h, w)
            widget.show()

        def add_trace_widgets(trace_widgets, row, extra=False):
            show(trace_widgets.icon, row, 0, 1, 1)
            show(trace_widgets.draw, row, 1, 1, 1)
            show(trace_widgets.hold, row, 2, 1, 1)
            if extra:
                show(trace_widgets.add_marker, row, 3, 1, 1)
            show(trace_widgets.remove, row, 4, 1, 1)
            return row + 1

        def add_trace_off_widgets(trace_widgets, row):
            show(trace_widgets.icon, row, 0, 1, 1)
            show(trace_widgets.add, row, 1, 1, 1)
            return row + 1

        def add_marker_widgets(marker_widgets, row):
            show(marker_widgets.marker, row, 0, 1, 2)
            show(marker_widgets.peak, row, 2, 1, 1)
            show(marker_widgets.center, row, 3, 1, 1)
            show(marker_widgets.remove, row, 4, 1, 1)
            row = row + 1
            show(marker_widgets.peak_left, row, 2, 1, 1)
            show(marker_widgets.peak_right, row, 3, 1, 1)
            return row + 1

        extra_markers = any(not m.enabled for m in self._plot.markers)

        row = 0
        for trace_index, (trace, widgets) in enumerate(
                zip(self._plot.traces, self._traces)):
            if trace.blank:
                row = add_trace_off_widgets(widgets, row)
                continue
            row = add_trace_widgets(widgets, row, extra_markers)

            trace_markers = [
                i for (i, marker) in enumerate(self._plot.markers)
                if marker.enabled and marker.trace_index == trace_index]
            if trace_markers:
                for tm in trace_markers:
                    row = add_marker_widgets(self._markers[tm], row)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 5)
        grid.setColumnStretch(2, 5)
        grid.setColumnStretch(3, 5)
        grid.setColumnStretch(4, 2)


    def state_changed(self, state, changed):
        if 'device_settings.iq_output_path' in changed:
            if state.device_settings['iq_output_path'] == 'CONNECTOR':
                self.hide()
            else:
                self.show()

    def capture_received(self, state, fstart, fstop, raw, power, usable, segments):
        # save x,y data for marker adjustments
        self.pow_data = power
        self.xdata = np.linspace(fstart, fstop, len(power))

    def _trace_tab_change(self):
        """
        change the selected trace
        """
        trace = self._plot.traces[self.trace_tab.currentIndex()]

        if trace.write:
            self.trace_attr['write'].click()
        elif trace.max_hold:
            self.trace_attr['max_hold'].click()
        elif trace.min_hold:
            self.trace_attr['min_hold'].click()
        elif trace.blank:
            self.trace_attr['blank'].click()

        if self._plot.traces[self.trace_tab.currentIndex()].store:
            state =  QtCore.Qt.CheckState.Checked
        else:
            state =  QtCore.Qt.CheckState.Unchecked
        self.trace_attr['store'].setCheckState(state)

    def max_hold(self, num):
        """
        disable/enable max hold on a trace
        """
        trace = self._plot.traces[num]
        trace.write = False
        trace.max_hold = True
        trace.min_hold = False
        trace.blank = False

    def min_hold(self, num):
        """
        disable/enable min hold on a trace
        """
        trace = self._plot.traces[num]
        trace.write = False
        trace.max_hold = False
        trace.min_hold = True
        trace.blank = False

    def trace_write(self, num):
        """
        disable/enable running FFT mode the selected trace
        """
        trace = self._plot.traces[num]
        trace.write = True
        trace.max_hold = False
        trace.min_hold = False
        trace.blank = False

    def blank_trace(self, num):
        """
        disable the selected trace
        """
        trace = self._plot.traces[num]
        trace.write = False
        trace.max_hold = False
        trace.min_hold = False
        trace.blank = True
        trace.clear()
        trace.data = None

        for marker in self._plot.markers:
            if marker.trace_index == num:
                marker.disable(self._plot)

    def _store_trace(self, num, store):
        """
        store the current trace's data
        """
        self._plot.traces[num].store = bool(store)

    def _marker_control(self):
        """
        disable/enable marker
        """
        marker = self._plot.markers[self._marker_tab.currentIndex()]
        if self._marker_check.checkState() is QtCore.Qt.CheckState.Checked:

            self._marker_trace.setEnabled(True)
            if self._marker_trace.currentIndex() < 0:
                self._marker_trace.setCurrentIndex(0)
            marker.trace_index = int(self._marker_trace.currentText()) - 1
            marker.enable(self._plot)
        else:
            self._marker_trace.setEnabled(False)
            self._plot.markers[self._marker_tab.currentIndex()].disable(self._plot)

            self.marker_labels[self._marker_tab.currentIndex()].setText('')

    def _marker_trace_control(self):
        """
        change the trace that is currently associated with the marker
        """

        if self._marker_trace is not None:
            marker = self._plot.markers[0]  # XXX
            if not self._marker_trace.currentText() == '':
                marker.trace_index = int(self._marker_trace.currentText()) - 1


    def _marker_tab_change(self):
        """
        change the current selected marker
        """

        for marker in self._plot.markers:
            marker.selected = False
        marker = self._plot.markers[self._marker_tab.currentIndex()]
        if marker.enabled:
            if marker.trace_index == 2:
                if self._marker_trace.count() == 2:
                    index = 1
                else:
                    index = 2
                self._marker_trace.setCurrentIndex(index)
            else:
                self._marker_trace.setCurrentIndex(marker.trace_index)
            self._marker_trace.setEnabled(True)
            self._marker_check.setCheckState(QtCore.Qt.CheckState.Checked)
        else:
            self._marker_trace.setEnabled(False)

            self._marker_trace.setCurrentIndex(marker.trace_index)
            self._marker_check.setCheckState(QtCore.Qt.CheckState.Unchecked)
        marker.selected = True

    def _find_peak(self, num):
        """
        move the selected marker to the maximum point of the spectrum
        """
        marker = self._plot.markers[num]

        # retrieve the min/max x-axis of the current window
        window_freq = self._plot.view_box.viewRange()[0]
        data_range = self.xdata
        if window_freq[-1] < data_range[0] or window_freq[0] > data_range[-1]:
            return

        min_index, max_index = np.searchsorted(data_range, (window_freq[0], window_freq[-1]))

        trace = self._plot.traces[marker.trace_index]
        peak_value = np.max(trace.data[min_index:max_index])
        marker.data_index = np.where(trace.data==peak_value)[0]

    def _find_right_peak(self, num):
        """
        move the selected marker to the next peak on the right
        """
        marker = self._plot.markers[num]
        trace = self._plot.traces[marker.trace_index]
        pow_data = trace.data

        # retrieve the min/max x-axis of the current window
        window_freq = self._plot.view_box.viewRange()[0]
        if marker.data_index is None:
            marker.data_index = len(pow_data) / 2
        data_range = self.xdata[marker.data_index:-1]

        if len(data_range) == 0:
            return

        if window_freq[-1] < data_range[0] or window_freq[0] > data_range[-1]:
            return
        min_index, max_index = np.searchsorted(data_range, (window_freq[0], window_freq[-1])) + marker.data_index

        right_pow = pow_data[min_index:max_index]

        # calculate noise floor level by averaging the maximum 80% of the fft
        noise_floor = np.mean(np.sort(right_pow)[int(len(right_pow) * ( 0.8)):-1])

        peak_values = np.ma.masked_less(right_pow, noise_floor + self.plot_state.peak_threshold).compressed()
        if len(peak_values) == 0:
            return
        marker.data_index = np.where(pow_data==(peak_values[1 if len(peak_values) > 1 else 0]))[0]

    def _find_left_peak(self, num):
        """
        move the selected marker to the next peak on the left
        """
        marker = self._plot.markers[num]
        trace = self._plot.traces[marker.trace_index]
        pow_data = trace.data
        # enable the marker if it is not already enabled
        if not marker.enabled:
            self._marker_check.click()

        # retrieve the min/max x-axis of the current window
        window_freq = self._plot.view_box.viewRange()[0]
        if marker.data_index is None:
            marker.data_index = len(pow_data) / 2
        data_range = self.xdata[0:marker.data_index]

        if len(data_range) == 0:
            return
        if window_freq[-1] < data_range[0] or window_freq[0] > data_range[-1]:
            return

        min_index, max_index = np.searchsorted(data_range, (window_freq[0], window_freq[-1]))
        left_pow = pow_data[min_index:max_index]

        # calculate noise floor level by averaging the maximum 80% of the fft
        noise_floor = np.mean(np.sort(left_pow)[int(len(left_pow) * ( 0.8)):-1])

        peak_values = np.ma.masked_less(left_pow, noise_floor + self.plot_state.peak_threshold).compressed()
        if len(peak_values) == 0:
            return
        marker.data_index = np.where(pow_data==(peak_values[-2 if len(peak_values) > 1 else -1]))[0]

    def _change_ref_level(self):
        """
        change the ref level (maximum of the y-axis) of the fft plot
        """
        try:
            ref = float(self._ref_level.text())
        except ValueError:
            self.ref_level.setText(str(self.plot_state.ref_level))
            return
        self.plot_state.ref_level = ref

        _center_plot_view(self)

    def _change_min_level(self):
        """
        change the min level of the fft plot
        """
        try:
            min = float(self._min_level.text())
        except ValueError:
            self.min_level.setText(str(self.plot_state.min_level))
            return
        self.plot_state.min_level = min
        _center_plot_view(self)



    def _trace_items(self):

        trace_attr = {}
        store = QtGui.QCheckBox('Store')
        store.setEnabled(False)
        trace_attr['store'] = store

        max_hold = QtGui.QRadioButton('Max Hold')
        trace_attr['max_hold'] = max_hold

        min_hold = QtGui.QRadioButton('Min Hold')
        trace_attr['min_hold'] = min_hold

        write = QtGui.QRadioButton('Write')
        trace_attr['write'] = write

        blank = QtGui.QRadioButton('Blank')
        trace_attr['blank'] = blank

        self.trace_attr = trace_attr
        self.trace_attr['write'].click()
        return max_hold, min_hold, write, store, blank


    def plot_controls(self):

        plot_group = QtGui.QGroupBox("Plot Control")
        self._plot_group = plot_group

        plot_controls_layout = QtGui.QVBoxLayout()

        self.control_widgets = []

        fourth_row = QtGui.QHBoxLayout()
        ref_level, ref_label, min_level, min_label = self._ref_controls()

        fourth_row.addWidget(ref_label)
        fourth_row.addWidget(ref_level)
        fourth_row.addWidget(min_label)
        fourth_row.addWidget(min_level)

        plot_controls_layout.addLayout(fourth_row)
        plot_group.setLayout(plot_controls_layout)

        return plot_group

    def _center_control(self):
        center = QtGui.QPushButton('Recenter')
        center.setToolTip("[C]\nCenter the Plot View around the available spectrum")
        center.clicked.connect(lambda: self._plot.center_view(min(self.xdata),
                                                            max(self.xdata),
                                                            min_level = int(self._min_level.text()),
                                                            ref_level = int(self._ref_level.text())))
        self._center_bt = center
        self.control_widgets.append(self._center_bt)
        return center

    def _ref_controls(self):
        ref_level = QtGui.QLineEdit(str(PLOT_YMAX))
        ref_level.returnPressed.connect(lambda: self._plot.center_view(min(self.xdata),
                                                                        max(self.xdata),
                                                                        min_level = int(self._min_level.text()),
                                                                        ref_level = int(self._ref_level.text())))
        self._ref_level = ref_level
        self.control_widgets.append(self._ref_level)
        ref_label = QtGui.QLabel('Maximum Level: ')

        min_level = QtGui.QLineEdit(str(PLOT_YMIN))
        min_level.returnPressed.connect(lambda: self._plot.center_view(min(self.xdata),
                                                                        max(self.xdata),
                                                                        min_level = int(self._min_level.text()),
                                                                        ref_level = int(self._ref_level.text())))
        min_label = QtGui.QLabel('Minimum Level: ')
        self._min_level = min_level
        self.control_widgets.append(self._min_level)
        return ref_level, ref_label, min_level, min_label

