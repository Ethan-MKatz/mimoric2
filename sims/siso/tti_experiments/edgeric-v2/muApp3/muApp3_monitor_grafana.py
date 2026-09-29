import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from edgeric_messenger import EdgericMessenger
import threading
import time
import numpy as np

#########################
from prometheus_client import start_http_server, Gauge
import threading
#########################

class PrometheusMonitor:
    def __init__(self, port=8000):

        self.messenger = EdgericMessenger("")

        self.port = port
        self.ue_dict = {}
        self.tx_bytes_history = {}
        self.rx_bytes_history = {}
        self.dl_buffer_history = {}
        self.ul_buffer_history = {}
        self.first_tti = {}

        # Initialize Prometheus metrics
        self.cqi_gauge = Gauge('ue_cqi', 'UE Channel Quality Indicator', ['rnti'])
        self.snr_gauge = Gauge('ue_snr', 'UE Signal-to-Noise Ratio', ['rnti'])
        #self.dl_bytes_gauge = Gauge('ue_dl_bytes', 'UE Downlink Bytes', ['rnti'])
        #self.ul_bytes_gauge = Gauge('ue_ul_bytes', 'UE Uplink Bytes', ['rnti'])
        #self.dl_buffer_gauge = Gauge('ue_dl_buffer', 'UE Downlink Buffer', ['rnti'])
        #self.ul_buffer_gauge = Gauge('ue_ul_buffer', 'UE Uplink Buffer', ['rnti'])
        #self.dl_tbs_gauge = Gauge('ue_dl_tbs', 'UE Downlink TBS', ['rnti'])
        #self.tti_count_gauge = Gauge('ran_tti_count', 'RAN TTI Count')
        self.avg_dl_buffer_gauge = Gauge('ue_avg_dl_buffer', 'UE Average DL Buffer', ['rnti'])
        self.avg_ul_buffer_gauge = Gauge('ue_avg_ul_buffer', 'UE Average UL Buffer', ['rnti'])
        self.avg_tx_throughput_gauge = Gauge('ue_avg_tx_throughput', 'UE Average TX Throughput', ['rnti'])
        self.avg_rx_throughput_gauge = Gauge('ue_avg_rx_throughput', 'UE Average RX Throughput', ['rnti'])
        

        self.avg_tot_dl_buffer_gauge = Gauge('tot_avg_dl_buffer', 'tot Average DL Buffer', ['non'])
        self.avg_tot_ul_buffer_gauge = Gauge('tot_avg_ul_buffer', 'tot Average UL Buffer', ['non'])
        self.avg_tot_tx_throughput_gauge = Gauge('tot_avg_tx_throughput', 'tot Average TX Throughput', ['non'])
        self.avg_tot_rx_throughput_gauge = Gauge('tot_avg_rx_throughput', 'tot Average RX Throughput', ['non'])

        # MIMO-RIC: per-rx-antenna UL channel power. ul_channel arrives flattened
        # as nrx x nsc x (re,im); collapsing each antenna to a power in dB gives
        # one series per rx antenna, which is what shows the 4x4 is really live.
        self.ul_channel_power_gauge = Gauge('ue_ul_channel_power_db', 'UE per-rx-antenna UL channel power (dB)', ['rnti', 'rx'])
        self.ul_channel_nrx_gauge = Gauge('ue_ul_channel_nrx', 'UE rx antennas reporting UL channel', ['rnti'])

        # MIMO-RIC: continuous dump of the ZMQ channel reports to disk. Prometheus keeps
        # only the newest value per series, so anything to be compared offline has to be
        # appended as it arrives. Written under the ./edgeric-v2 bind mount so the files
        # land on the host.
        self.chan_log_dir = os.environ.get("TT_CHAN_LOG_DIR", "/home/EdgeRIC/results")
        self.chan_log_every = max(1, int(os.environ.get("TT_CHAN_LOG_EVERY", "1")))
        self.chan_log_raw = os.environ.get("TT_CHAN_LOG_RAW", "0") == "1"
        self.chan_rx_count = 0
        self.chan_pow_file = None
        self.chan_raw_file = None
        if os.environ.get("TT_CHAN_LOG", "1") != "0":
            os.makedirs(self.chan_log_dir, exist_ok=True)
            stamp = os.environ.get("TT_CHAN_LOG_TAG") or time.strftime("%Y%m%d-%H%M%S")
            pow_path = os.path.join(self.chan_log_dir, f"ul_channel_power_{stamp}.txt")
            self.chan_pow_file = open(pow_path, "w", buffering=1)
            self.chan_pow_file.write("wallclock,tti,rnti,nrx,nsc,rx,power_db\n")
            print(f"[MIMO-RIC] logging per-antenna channel power to {pow_path}", flush=True)
            if self.chan_log_raw:
                raw_path = os.path.join(self.chan_log_dir, f"ul_channel_raw_{stamp}.txt")
                self.chan_raw_file = open(raw_path, "w", buffering=1)
                # variable-width: header names the fixed prefix, then nrx*nsc*2 floats
                self.chan_raw_file.write("wallclock,tti,rnti,nrx,nsc,samples[rx][sc][re,im]...\n")
                print(f"[MIMO-RIC] logging raw channel samples to {raw_path}", flush=True)

        start_http_server(self.port)


    def update_metrics(self):
        while True:
            self.tti_count, self.ue_dict = self.messenger.get_metrics(True)
            self.chan_rx_count += 1
            #self.tti_count_gauge.set(self.ran_tti)
            avg_tx_throughput_tot=[]
            avg_rx_throughput_tot=[]
            avg_dl_buffer_tot=[]
            avg_ul_buffer_tot=[]
            for rnti, metrics in self.ue_dict.items():
                if rnti not in self.first_tti.keys():
                    #print("hiiii")
                    self.first_tti[rnti] = self.tti_count
                    #print(self.first_tti)
                avg_tx_throughput, avg_rx_throughput, avg_dl_buffer, avg_ul_buffer = self.calculate_moving_avg(rnti=rnti,metrics=metrics)
                
                avg_tx_throughput_tot.append(avg_tx_throughput)
                avg_rx_throughput_tot.append(avg_rx_throughput)
                avg_dl_buffer_tot.append(avg_dl_buffer)
                avg_ul_buffer_tot.append(avg_ul_buffer)

                self.cqi_gauge.labels(rnti=rnti).set(metrics['cqi'])
                self.snr_gauge.labels(rnti=rnti).set(metrics['snr'])
                self.avg_tx_throughput_gauge.labels(rnti=rnti).set(avg_tx_throughput)
                self.avg_rx_throughput_gauge.labels(rnti=rnti).set(avg_rx_throughput)
                self.avg_dl_buffer_gauge.labels(rnti=rnti).set(avg_dl_buffer)
                self.avg_ul_buffer_gauge.labels(rnti=rnti).set(avg_ul_buffer)
                self.publish_ul_channel(rnti, metrics)

            self.avg_tot_tx_throughput_gauge.labels(non=1).set(sum(avg_tx_throughput_tot))
            self.avg_tot_rx_throughput_gauge.labels(non=1).set(sum(avg_rx_throughput_tot))
            self.avg_tot_dl_buffer_gauge.labels(non=1).set(sum(avg_dl_buffer_tot))
            self.avg_tot_ul_buffer_gauge.labels(non=1).set(sum(avg_ul_buffer_tot))
                # self.dl_bytes_gauge.labels(rnti=rnti).set(metrics['tx_bytes'])
                # self.ul_bytes_gauge.labels(rnti=rnti).set(metrics['rx_bytes'])
                # self.dl_buffer_gauge.labels(rnti=rnti).set(metrics['dl_buffer'])
                # self.ul_buffer_gauge.labels(rnti=rnti).set(metrics['ul_buffer'])
                # self.dl_tbs_gauge.labels(rnti=rnti).set(metrics['dl_tbs'])

            

    def publish_ul_channel(self, rnti, metrics):
        """Collapse the flattened ul_channel into one power-in-dB series per rx antenna."""
        chan = metrics.get('ul_channel') or []
        nrx = metrics.get('ul_channel_nrx') or 0
        nsc = metrics.get('ul_channel_nsc') or 0
        if not chan or nrx <= 0 or nsc <= 0:
            return
        self.ul_channel_nrx_gauge.labels(rnti=rnti).set(nrx)
        # expected layout: nrx * nsc * 2 floats (re, im)
        if len(chan) < nrx * nsc * 2:
            return
        arr = np.asarray(chan[:nrx * nsc * 2], dtype=np.float64).reshape(nrx, nsc, 2)
        power = (arr[:, :, 0] ** 2 + arr[:, :, 1] ** 2).mean(axis=1)
        db = [10.0 * np.log10(p) if p > 0 else -200.0 for p in power]
        for rx in range(nrx):
            self.ul_channel_power_gauge.labels(rnti=rnti, rx=rx).set(db[rx])
        self.log_ul_channel(rnti, nrx, nsc, db, chan)

    def log_ul_channel(self, rnti, nrx, nsc, db, chan):
        """Append this report to the txt logs, one row per rx antenna (plus raw if enabled)."""
        if self.chan_pow_file is None or (self.chan_rx_count % self.chan_log_every):
            return
        now = time.time()
        for rx in range(nrx):
            self.chan_pow_file.write(
                f"{now:.6f},{self.tti_count},{rnti},{nrx},{nsc},{rx},{db[rx]:.6f}\n")
        if self.chan_raw_file is not None:
            samples = ",".join(f"{v:.6g}" for v in chan[:nrx * nsc * 2])
            self.chan_raw_file.write(f"{now:.6f},{self.tti_count},{rnti},{nrx},{nsc},{samples}\n")

    def calculate_moving_avg(self, rnti, metrics):
      
        if rnti not in self.tx_bytes_history:
            self.tx_bytes_history[rnti] = []
        tx_bytes = metrics['tx_bytes']
        self.tx_bytes_history[rnti].append(tx_bytes)

        if rnti not in self.rx_bytes_history:
            self.rx_bytes_history[rnti] = []
        rx_bytes = metrics['rx_bytes']
        self.rx_bytes_history[rnti].append(rx_bytes)

        if rnti not in self.dl_buffer_history:
            self.dl_buffer_history[rnti] = []
        dl_buffer = metrics['dl_buffer']
        self.dl_buffer_history[rnti].append(dl_buffer)

        if rnti not in self.ul_buffer_history:
            self.ul_buffer_history[rnti] = []
        ul_buffer = metrics['ul_buffer']
        self.ul_buffer_history[rnti].append(ul_buffer)

        if (self.tti_count - self.first_tti[rnti]) >= 1000:
            total_time = 1
            total_tx_bytes = sum(self.tx_bytes_history[rnti])
            total_rx_bytes = sum(self.rx_bytes_history[rnti])
            total_dl_buffer = sum(self.dl_buffer_history[rnti])
            total_ul_buffer = sum(self.ul_buffer_history[rnti])
            avg_tx_throughput = (total_tx_bytes * 8) / total_time
            avg_rx_throughput = (total_rx_bytes * 8) / total_time
            avg_dl_buffer = (total_dl_buffer * 8) / (total_time*1000)
            avg_ul_buffer = (total_ul_buffer * 8) / (total_time*1000)
            self.tx_bytes_history[rnti].pop(0)
            self.rx_bytes_history[rnti].pop(0)
            self.dl_buffer_history[rnti].pop(0)
            self.ul_buffer_history[rnti].pop(0)
            #print(avg_tx_throughput,metrics['tx_bytes'])
        else:
            avg_tx_throughput = 0
            avg_rx_throughput = 0
            avg_dl_buffer = 0
            avg_ul_buffer = 0
        
        return avg_tx_throughput, avg_rx_throughput, avg_dl_buffer, avg_ul_buffer

if __name__ == "__main__":
    monitor = PrometheusMonitor()

    # Create and start the periodic sending thread
    monitoring_thread = threading.Thread(target=monitor.update_metrics)
    monitoring_thread.start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping the weight sending script.")