"""Android-only features (steps, screen time, sharing). Safe no-ops on desktop."""
import datetime, time
from kivy.utils import platform

ON = platform == "android"
if ON:
    from jnius import autoclass, cast, PythonJavaClass, java_method
    from android.permissions import request_permissions
    PA = autoclass("org.kivy.android.PythonActivity")


def ask_permissions():
    if ON:
        request_permissions(["android.permission.ACTIVITY_RECOGNITION"])


class Steps:
    """Reads Android's cumulative step counter and passes the value to cb."""
    def __init__(self, cb):
        self.cb, self.ok, self.keep = cb, False, None

    def start(self):
        if not ON or self.ok:
            return
        try:
            from kivy.clock import Clock
            sm = PA.mActivity.getSystemService("sensor")
            sensor = sm.getDefaultSensor(19)  # TYPE_STEP_COUNTER
            if sensor is None:
                return
            cb = self.cb

            class L(PythonJavaClass):
                __javainterfaces__ = ["android/hardware/SensorEventListener"]
                __javacontext__ = "app"

                @java_method("(Landroid/hardware/SensorEvent;)V")
                def onSensorChanged(self, e):
                    Clock.schedule_once(lambda _dt, v=e.values[0]: cb(v))

                @java_method("(Landroid/hardware/Sensor;I)V")
                def onAccuracyChanged(self, s, a):
                    pass

            self.keep = L()
            self.ok = bool(sm.registerListener(self.keep, sensor, 3))
        except Exception as ex:
            print("steps error:", ex)


def has_usage_access():
    if not ON:
        return False
    ctx = PA.mActivity
    ops = ctx.getSystemService("appops")
    return ops.checkOpNoThrow("android:get_usage_stats",
                              ctx.getApplicationInfo().uid,
                              ctx.getPackageName()) == 0


def open_usage_settings():
    if ON:
        Intent = autoclass("android.content.Intent")
        PA.mActivity.startActivity(Intent("android.settings.USAGE_ACCESS_SETTINGS"))


def screen_minutes():
    """Minutes any app was in the foreground today (None if no access)."""
    try:
        if not has_usage_access():
            return None
        usm = PA.mActivity.getSystemService("usagestats")
        now = int(time.time() * 1000)
        mid = int(datetime.datetime.combine(datetime.date.today(),
                                            datetime.time()).timestamp() * 1000)
        lst = usm.queryUsageStats(0, mid, now)
        tot = 0
        for i in range(lst.size()):
            s = cast("android.app.usage.UsageStats", lst.get(i))
            tot += s.getTotalTimeInForeground()
        return tot // 60000
    except Exception as ex:
        print("usage error:", ex)
        return None


def export_dir():
    if ON:
        return PA.mActivity.getExternalFilesDir(None).getAbsolutePath()
    return None


def share(text, subject="LifeLog export"):
    if not ON:
        return
    Intent = autoclass("android.content.Intent")
    String = autoclass("java.lang.String")
    i = Intent(Intent.ACTION_SEND)
    i.setType("text/plain")
    i.putExtra(Intent.EXTRA_SUBJECT, String(subject))
    i.putExtra(Intent.EXTRA_TEXT, cast("java.lang.CharSequence", String(text)))
    PA.mActivity.startActivity(Intent.createChooser(i, String("Export data")))


def battery_temp():
    """Battery temperature in deg C (the phone's only widely available temperature sensor)."""
    if not ON:
        return None
    try:
        IF = autoclass("android.content.IntentFilter")
        Intent = autoclass("android.content.Intent")
        i = PA.mActivity.registerReceiver(None, IF(Intent.ACTION_BATTERY_CHANGED))
        t = i.getIntExtra("temperature", -1)
        return t / 10.0 if t > 0 else None
    except Exception as ex:
        print("temp error:", ex)
        return None


def http_get_json(url, ok, fail):
    """Download JSON in a background thread. Calls ok(data) or fail() on the Kivy thread."""
    import json, threading
    from kivy.clock import Clock

    def work():
        try:
            if ON:  # Android's Java stack handles HTTPS, so Python needs no OpenSSL
                URL = autoclass("java.net.URL")
                BR = autoclass("java.io.BufferedReader")
                ISR = autoclass("java.io.InputStreamReader")
                c = URL(url).openConnection()
                c.setConnectTimeout(10000)
                c.setReadTimeout(10000)
                r = BR(ISR(c.getInputStream()))
                parts, line = [], r.readLine()
                while line is not None:
                    parts.append(line)
                    line = r.readLine()
                r.close()
                text = "".join(parts)
            else:
                from urllib.request import urlopen
                text = urlopen(url, timeout=10).read().decode()
            data = json.loads(text)
            Clock.schedule_once(lambda _dt: ok(data))
        except Exception as ex:
            print("http error:", ex)
            Clock.schedule_once(lambda _dt: fail())

    threading.Thread(target=work, daemon=True).start()
