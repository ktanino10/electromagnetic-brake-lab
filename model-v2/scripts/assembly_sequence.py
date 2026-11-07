"""Prescribed assembly motion, in CAD mm. No dynamics, contacts or magnetic forces."""
import math

DURATION = 88
FPS = 12
STAGES = [
    (0, "準備", "部品とM3ねじをそろえる", "印刷部品6種＋金属ねじ類。これは組立手順のCGです。"),
    (6, "1 / 10", "コイル役リングを台座の溝へ", "オレンジは電磁石の位置を示すプラスチック。磁力はありません。"),
    (10.5, "2 / 10", "柱の横溝にナットを入れる", "上から下ろして横へスライド。後でM3×25を受けます。"),
    (18, "3 / 10", "ナットを置き、円盤とハブをかぶせる", "別の作業面で組みます。裏側の六角穴がナットの回り止めになります。"),
    (25, "4 / 10", "板ばね3枚を渡す", "紫のハブと青い円盤を、両端の穴でつなぎます。"),
    (29, "5 / 10", "平座金とM3×6で固定", "右回しで進み、最後にナットが上がります。締付けトルクは未検証。"),
    (41, "6 / 10", "回る部分をまとめて柱に通す", "ハブの軸穴Ø8.7と柱Ø8.0。片側の名目すき間は0.35mm。"),
    (47, "7 / 10", "キャップとM3×25で抜け止め", "平座金を挟み、柱の横溝のナットへねじ込みます。"),
    (56, "8 / 10", "押していない状態：手で回す", "板ばねが円盤を浮かせます。模型の名目すき間は1.5mm。"),
    (61, "9 / 10", "円盤を押す → 離す", "本物の吸引力の代わりに指で押す想定。戻り方・摩擦は未実測。"),
    (71, "10 / 10", "断面：板ばねが曲がり、円盤が下がる", "青い円盤が灰色の固定面に接触。オレンジのリングには当たりません。"),
    (84, "完成形のCG", "組み合わせを理解するための模型", "未印刷・未購入・実物未検証。ねじ山は表示用、ナットの内ねじは省略。"),
]


def progress(t, a, b):
    return min(1.0, max(0.0, (t - a) / (b - a)))


def ease(t, a, b):
    u = progress(t, a, b)
    return u * u * (3 - 2 * u)


def mix(a, b, u):
    return [x + (y - x) * u for x, y in zip(a, b)]


def stage_at(t):
    return max(i for i, stage in enumerate(STAGES) if stage[0] <= t)


def press_at(t):
    return (ease(t, 63, 63.8) - ease(t, 67, 67.8)
            + ease(t, 74, 74.8) - ease(t, 79, 79.8))


class Sequence:
    def __init__(self, manifest, origins):
        self.man = manifest
        self.origins = origins
        self.names = list(manifest["render"])
        self.tags = ["hub0", "hub1", "hub2", "arm0", "arm1", "arm2"]
        self.work = [130, 0, -manifest["Z0"]]
        self.rotor = {n for n, d in manifest["render"].items() if d["group"] != "fixed"}
        self.kit = {}
        self.kitrot = {}
        for n in self.names:
            p = list(origins[n])
            if n == "coil":
                p = [-55, 125, 0]
            elif n == "armature":
                p = [55, 125, 0]
            elif n == "hub":
                p = [140, 125, 0]
            elif n.startswith("spring"):
                k = int(n[-1])
                p = [-80, 190 + 13 * k, 0]
                self.kitrot[n] = math.radians(-90 - manifest["strap_angles"][k])
            elif n == "cap":
                p = [-35, 200, 0]
            elif n.startswith(("nut_", "washer_", "screw_")):
                tag = n.split("_")[1]
                i = self.tags.index(tag) if tag in self.tags else 6
                if n.startswith("nut_"):
                    p = [-10 + 9 * i, 190, 0]
                elif n.startswith("washer_"):
                    p = [-10 + 9 * i, 205, 0]
                else:
                    p = [60 + 10 * i, 200, manifest["render"][n]["data"]["length"]]
            self.kit[n] = p

    def move(self, n, target, t, a, b):
        start = self.kit[n]
        u = ease(t, a, b)
        p = mix(start, target, u)
        # A lifted route, rather than a straight drag through other parts.
        if 0 < u < 1:
            p[2] += 65 * math.sin(math.pi * u)
        return p, self.kitrot.get(n, 0) * (1 - u)

    def poses(self, t):
        out = {}
        work = self.work
        for n, ent in self.man["render"].items():
            target = list(self.origins[n])
            p, rz = list(self.kit[n]), self.kitrot.get(n, 0)
            if n == "base":
                p = target
            elif n == "coil":
                p, rz = self.move(n, target, t, 7, 9.6)
            elif n == "nut_axle":
                a = math.radians(self.man["slot_deg"])
                radial = [16 * math.cos(a), 16 * math.sin(a), 12]
                if t < 14.6:
                    p, rz = self.move(n, radial, t, 11.5, 14.6)
                else:
                    p = mix(radial, [0, 0, 12], ease(t, 14.8, 16.2))
                    p[2] += 0.2 * progress(t, 52.4 + 2.8 * 6.2 / 6.6, 55.2)
            elif n in self.rotor:
                target = [x + y for x, y in zip(target, work)]
                if n in ("armature", "hub"):
                    a, b = (22.2, 23.8) if n == "armature" else (23.4, 24.8)
                    p, rz = self.move(n, target, t, a, b)
                elif n.startswith("spring"):
                    k = int(n[-1])
                    p, rz = self.move(n, target, t, 25.2 + k * 0.5, 27 + k * 0.5)
                else:
                    kind, tag = n.split("_")
                    i = self.tags.index(tag)
                    start = 34.2 if tag.startswith("hub") else 35.6
                    if kind == "nut":
                        target[2] -= 0.8
                        p, rz = self.move(n, target, t, 19 + 0.35 * i, 20.6 + 0.35 * i)
                        p[2] += 0.8 * progress(t, start + 2.1333333333, start + 3.2)
                    elif kind == "washer":
                        p, rz = self.move(n, target, t, 29.4 + 0.25 * i, 30.9 + 0.25 * i)
                    elif kind == "screw":
                        target[2] += 1.6
                        p, rz = self.move(n, target, t, 31 + 0.25 * i, 32.8 + 0.25 * i)
                        turns = 4.8 * progress(t, start, start + 3.2)
                        p[2] -= min(1.6, turns * self.man["pitch"])
                        rz -= turns * 2 * math.pi
                if t >= 42:
                    transfer = mix(work, [130, 0, 30], ease(t, 42, 43))
                    if t >= 43:
                        transfer = mix([130, 0, 30], [0, 0, 30], ease(t, 43, 44.6))
                    if t >= 44.6:
                        transfer = mix([0, 0, 30], [0, 0, 0], ease(t, 44.6, 46.2))
                    p = [x - y + z for x, y, z in zip(p, work, transfer)]
                theta = -2 * math.pi * ease(t, 57.2, 60.2)
                x, y = p[:2]
                p[:2] = [x * math.cos(theta) - y * math.sin(theta),
                         x * math.sin(theta) + y * math.cos(theta)]
                rz += theta
                if ent["group"] == "armature":
                    p[2] -= self.man["delta"] * press_at(t)
            elif n == "cap":
                p, rz = self.move(n, target, t, 48, 49.6)
            elif n == "washer_axle":
                p, rz = self.move(n, target, t, 49.4, 50.8)
            elif n == "screw_axle":
                target[2] += 3.1
                p, rz = self.move(n, target, t, 50.6, 52.2)
                turns = 6.6 * progress(t, 52.4, 55.2)
                p[2] -= min(3.1, turns * self.man["pitch"])
                rz -= turns * 2 * math.pi
            out[n] = [*p, rz]
        return out
