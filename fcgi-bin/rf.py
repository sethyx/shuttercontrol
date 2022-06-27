import logging
import time
from collections import namedtuple

from RPi import GPIO

_LOGGER = logging.getLogger(__name__)

RFProtocol = namedtuple('RFProtocol',
                      ['pulselength', 'repeat_delay',
                       'sync_count', 'sync_delay',
                       'sync_high', 'sync_low',
                       'zero_high', 'zero_low',
                       'one_high', 'one_low'])

PROTOCOLS = (None,
             RFProtocol(40, 9600, 1, 0, 4750, 1550, 8, 19, 17, 10), # "home smart" shutter
             RFProtocol(40, 15200, 12, 3500, 360, 400, 9, 20, 18, 10) # garage door, doesn't work due to rolling code
             )

DEVICE_CODES = {
                "kitchen": {
                            "up": 95357333777,
                            "down": 95357333811,
                            "stop": 95357333845
                            },
                "lroom_l": {
                            "up": 653685920017,
                            "down": 653685920051,
                            "stop": 653685920085
                            },
                "lroom_m": {
                            "up": 181260607761,
                            "down": 181260607795,
                            "stop": 181260607829
                            },
                "lroom_r": {
                            "up": 99640512785,
                            "down": 99640512819,
                            "stop": 99640512853
                            },
                "house": { # special code that controls all shutters
                            "up": 86755979281,
                            "down": 86755979315,
                            "stop": 86755979349
                         }
                      }

class RFDevice:

    def __init__(self, gpio=17,
                 tx_proto=1, tx_pulselength=None, tx_repeat=8, tx_length=40):
        """Initialize the RF device."""
        self.gpio = gpio
        self.tx_enabled = False
        self.tx_proto = tx_proto
        if tx_pulselength:
            self.tx_pulselength = tx_pulselength
        else:
            self.tx_pulselength = PROTOCOLS[tx_proto].pulselength
        self.tx_repeat_delay = PROTOCOLS[tx_proto].repeat_delay
        self.tx_sync_count = PROTOCOLS[tx_proto].sync_count
        self.tx_sync_delay = PROTOCOLS[tx_proto].sync_delay
        self.tx_repeat = tx_repeat
        self.tx_length = tx_length

        GPIO.setmode(GPIO.BCM)
        _LOGGER.debug("Using GPIO " + str(gpio))

    def cleanup(self):
        """Disable TX and clean up GPIO."""
        if self.tx_enabled:
            self.disable_tx()
        _LOGGER.debug("Cleanup")
        GPIO.cleanup()

    def enable_tx(self):
        """Enable TX, set up GPIO."""
        if not self.tx_enabled:
            self.tx_enabled = True
            GPIO.setup(self.gpio, GPIO.OUT)
            _LOGGER.debug("TX enabled")
        return True

    def disable_tx(self):
        """Disable TX, reset GPIO."""
        if self.tx_enabled:
            # set up GPIO pin as input for safety
            GPIO.setup(self.gpio, GPIO.IN)
            self.tx_enabled = False
            _LOGGER.debug("TX disabled")
        return True

    def tx_code(self, codes, tx_proto=None, tx_pulselength=None, tx_length=40):
        """
        Send a decimal code.
        Optionally set protocol, pulselength and code length.
        When none given reset to default protocol, default pulselength and set code length to 40 bits.
        """
        if tx_proto:
            self.tx_proto = tx_proto
        else:
            self.tx_proto = 1
        if tx_pulselength:
            self.tx_pulselength = tx_pulselength
        elif not self.tx_pulselength:
            self.tx_pulselength = PROTOCOLS[self.tx_proto].pulselength
        if tx_length:
            self.tx_length = tx_length
        rawcodes = []
        for code in codes:
            rawcode = format(code, '#0{}b'.format(self.tx_length + 2))[2:]
            _LOGGER.debug("TX code: " + str(rawcode))
            rawcodes.append(rawcode)
        return self._tx_bin(rawcodes)

    def _tx_bin(self, rawcodes):
        """Send a binary code, consider sync, delay and repeat parameters based on protocol."""
        _LOGGER.debug("TX bin: {}" + str(rawcodes))
        sent = ""

        for code in rawcodes:
            for _ in range(0, self.tx_repeat):
                for x in range(self.tx_sync_count):
                    sent += "$"
                    if not self._tx_sync():
                        return False
                if (self.tx_sync_delay > 0):
                    sent += "&"
                    if not self._tx_delay(self.tx_sync_delay):
                        return False
                for byte in range(0, self.tx_length):
                    if code[byte] == '0':
                        sent += "0"
                        if not self._tx_l0():
                            return False
                    else:
                        sent += "1"
                        if not self._tx_l1():
                            return False
                sent += "|"
                if not self._tx_delay(self.tx_repeat_delay):
                    return False
        #_LOGGER.debug("sent: {}".format(sent))
        return True

    def _tx_l0(self):
        """Send a '0' bit."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error("Unknown TX protocol")
            return False
        return self._tx_waveform(PROTOCOLS[self.tx_proto].zero_high,
                                PROTOCOLS[self.tx_proto].zero_low)

    def _tx_l1(self):
        """Send a '1' bit."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error("Unknown TX protocol")
            return False
        return self._tx_waveform(PROTOCOLS[self.tx_proto].one_high,
                                PROTOCOLS[self.tx_proto].one_low)

    def _tx_sync(self):
        """Send a sync."""
        if not 0 < self.tx_proto < len(PROTOCOLS):
            _LOGGER.error("Unknown TX protocol")
            return False
        return self._tx_waveform_irregular(PROTOCOLS[self.tx_proto].sync_high,
                                PROTOCOLS[self.tx_proto].sync_low)

    def _tx_delay(self, delay):
        """Wait between repeats."""
        if not self.tx_enabled:
            _LOGGER.error("TX is not enabled, not sending data")
            return False
        GPIO.output(self.gpio, GPIO.LOW)
        self._sleep((delay) / 1000000)
        return True

    def _tx_waveform(self, highpulses, lowpulses):
        """Send basic waveform."""
        if not self.tx_enabled:
            _LOGGER.error("TX is not enabled, not sending data")
            return False
        GPIO.output(self.gpio, GPIO.HIGH)
        self._sleep((highpulses * self.tx_pulselength) / 1000000)
        GPIO.output(self.gpio, GPIO.LOW)
        self._sleep((lowpulses * self.tx_pulselength) / 1000000)
        return True

    def _tx_waveform_irregular(self, highpulses, lowpulses):
        """Send waveform without using regular pulse length."""
        if not self.tx_enabled:
            _LOGGER.error("TX is not enabled, not sending data")
            return False
        GPIO.output(self.gpio, GPIO.HIGH)
        self._sleep((highpulses) / 1000000)
        GPIO.output(self.gpio, GPIO.LOW)
        self._sleep((lowpulses) / 1000000)
        return True

    def _sleep(self, delay):      
        _delay = delay / 100
        end = time.time() + delay - _delay
        while time.time() < end:
            time.sleep(_delay)

    def tx_shutter_cmd(self, device, command):
        """Send command(s) to shutter device(s)."""
        command_list = []

        for dev in DEVICE_CODES:
            if device in dev:
                cmd = DEVICE_CODES.get(dev).get(command)
                if (cmd):
                    command_list.append(cmd)

        if (command_list):
            self.enable_tx()
            self.tx_code(command_list)
            self.cleanup()
        return True
