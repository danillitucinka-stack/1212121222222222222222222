from __future__ import annotations

import json
import math
import random
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle, RoundedRectangle, Triangle
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget


SAVE_PATH = Path("sky_collector_save.json")

C_BG = (0.06, 0.09, 0.16, 1)
C_STAR = (1.0, 0.85, 0.35, 1)
C_GEM = (0.35, 0.95, 0.6, 1)
C_BOMB = (0.92, 0.35, 0.35, 1)
C_CLOCK = (0.95, 0.95, 0.98, 1)
C_PLAYER = (0.35, 0.7, 1.0, 1)
C_WING = (0.7, 0.5, 1.0, 1)
C_WHITE = (1, 1, 1, 1)

STAR_SPIKES = 5
GEM_SPIKES = 4


def make_star_verts(cx: float, cy: float, radius: float, spikes: int, angle: float = 0) -> list[float]:
    verts = [cx, cy, 0, 0]
    inner = radius * 0.45
    total = spikes * 2
    for i in range(total + 1):
        r = radius if i % 2 == 0 else inner
        a = angle + i * math.pi / spikes - math.pi / 2
        verts.extend([cx + math.cos(a) * r, cy + math.sin(a) * r, 0, 0])
    return verts


class FallingObject:
    def __init__(self, kind: str, x: float, y: float, speed: float, size: float) -> None:
        self.kind = kind
        self.x = x
        self.y = y
        self.speed = speed
        self.size = size
        self.angle = random.uniform(0, math.tau)
        self.spin = random.uniform(-4.5, 4.5)

    @property
    def radius(self) -> float:
        return self.size / 2

    def update(self, dt: float) -> None:
        self.y -= self.speed * dt
        self.angle += self.spin * dt

    def collides_with(self, px: float, py: float, pw: float, ph: float) -> bool:
        return px <= self.x <= px + pw and py <= self.y <= py + ph + self.radius


class FloatingText:
    def __init__(self, x: float, y: float, text: str, color: tuple) -> None:
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.life = 1.0
        self.dy = 120

    def update(self, dt: float) -> None:
        self.y += self.dy * dt
        self.life -= dt

    @property
    def alive(self) -> bool:
        return self.life > 0


class GameWidget(Widget):
    score = NumericProperty(0)
    best_score = NumericProperty(0)
    energy = NumericProperty(5)
    level = NumericProperty(1)
    combo = NumericProperty(0)
    game_state = StringProperty("menu")
    message = StringProperty("Tap to start")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.player_w = 120
        self.player_h = 26
        self._player_x = 0.0
        self._player_y = 90.0
        self._target_x = 0.0
        self.spawn_timer = 0.0
        self.spawn_delay = 0.8
        self.flash_timer = 0.0
        self.shake_timer = 0.0
        self.shake_offset = [0, 0]
        self.distance = 0.0
        self.objects: list[FallingObject] = []
        self.floating_texts: list[FloatingText] = []
        self.bg_stars: list[tuple[float, float, float]] = []
        self.best_score = self.load_best_score()
        self._needs_redraw = True
        self.lerp_speed = 18.0

        self.bind(size=self._on_size, pos=self._on_size)
        Clock.schedule_interval(self._update, 1 / 60)
        self._on_size()

    def _on_size(self, *_args) -> None:
        self._player_x = self.center_x - self.player_w / 2
        self._target_x = self._player_x
        self._player_y = max(70, self.height * 0.08)
        self.bg_stars = [(random.uniform(0, self.width), random.uniform(0, self.height), random.uniform(1.5, 4.0)) for _ in range(48)]
        self._needs_redraw = True

    def load_best_score(self) -> int:
        if SAVE_PATH.exists():
            try:
                return max(0, json.loads(SAVE_PATH.read_text("utf-8")).get("best_score", 0))
            except Exception:
                return 0
        return 0

    def save_best_score(self) -> None:
        SAVE_PATH.write_text(json.dumps({"best_score": self.best_score}), "utf-8")

    def reset_game(self) -> None:
        self.score = 0
        self.energy = 5
        self.level = 1
        self.combo = 0
        self.spawn_timer = 0.0
        self.spawn_delay = 0.8
        self.flash_timer = 0.0
        self.shake_timer = 0.0
        self.shake_offset = [0, 0]
        self.distance = 0.0
        self.objects.clear()
        self.floating_texts.clear()
        self.game_state = "playing"
        self.message = "Collect stars, dodge bombs"
        self._needs_redraw = True

    def _start_if_needed(self) -> None:
        if self.game_state in {"menu", "game_over"}:
            self.reset_game()

    def on_touch_down(self, touch):
        self._start_if_needed()
        self._target_x = touch.x - self.player_w / 2
        self._clamp_target()
        return True

    def on_touch_move(self, touch):
        if self.game_state == "playing":
            self._target_x = touch.x - self.player_w / 2
            self._clamp_target()
        return True

    def _clamp_target(self) -> None:
        self._target_x = max(12, min(self.width - self.player_w - 12, self._target_x))

    def _spawn_object(self) -> None:
        kind = random.choices(
            ["star", "gem", "bomb", "clock"],
            weights=[65, 16, 12 + self.level, 7],
            k=1,
        )[0]
        x = random.uniform(30, max(31, self.width - 30))
        y = self.height + 40
        speed = random.uniform(260 + self.level * 18, 390 + self.level * 22)
        size = 34 if kind != "bomb" else 40
        self.objects.append(FallingObject(kind, x, y, speed, size))

    def _add_floating_text(self, x: float, y: float, text: str, color: tuple) -> None:
        self.floating_texts.append(FloatingText(x, y, text, color))

    def _handle_collision(self, obj: FallingObject) -> None:
        fx, fy = obj.x, obj.y - 20
        if obj.kind == "star":
            self.score += 1
            self.combo += 1
            if self.combo % 10 == 0:
                self.score += 3
                self._add_floating_text(fx, fy, "+4 COMBO", C_GEM)
            else:
                self._add_floating_text(fx, fy, "+1", C_STAR)
        elif obj.kind == "gem":
            self.score += 5
            self.combo += 1
            self.flash_timer = 0.12
            self._add_floating_text(fx, fy, "+5 GEM", C_GEM)
        elif obj.kind == "clock":
            self.energy = min(5, self.energy + 1)
            self.score += 2
            self.combo += 1
            self._add_floating_text(fx, fy, "+1 HP", C_CLOCK)
        elif obj.kind == "bomb":
            self.energy -= 2
            self.combo = 0
            self.flash_timer = 0.25
            self.shake_timer = 0.2
            self._add_floating_text(fx, fy, "BOMB!", C_BOMB)

    def _miss_object(self, obj: FallingObject) -> None:
        if obj.kind != "bomb":
            self.energy -= 1
            self.combo = 0
            self._add_floating_text(self.center_x, self._player_y + 40, "MISS", (0.8, 0.8, 0.8, 1))

    def _update(self, dt: float) -> None:
        if self.game_state != "playing":
            self._redraw()
            return

        dt = min(dt, 0.05)

        dx = self._target_x - self._player_x
        self._player_x += dx * min(1, self.lerp_speed * dt)

        self.distance += dt * 10
        self.level = 1 + self.score // 30
        self.spawn_delay = max(0.22, 0.8 - self.level * 0.03)

        self.spawn_timer += dt
        while self.spawn_timer >= self.spawn_delay:
            self.spawn_timer -= self.spawn_delay
            self._spawn_object()

        for obj in self.objects[:]:
            obj.update(dt)
            if obj.collides_with(self._player_x, self._player_y, self.player_w, self.player_h):
                self._handle_collision(obj)
                self.objects.remove(obj)
                continue
            if obj.y < -50:
                self._miss_object(obj)
                self.objects.remove(obj)

        for ft in self.floating_texts[:]:
            ft.update(dt)
            if not ft.alive:
                self.floating_texts.remove(ft)

        if self.flash_timer > 0:
            self.flash_timer -= dt
        if self.shake_timer > 0:
            self.shake_timer -= dt
            self.shake_offset = [random.uniform(-6, 6), random.uniform(-6, 6)]
        else:
            self.shake_offset = [0, 0]

        if self.energy <= 0:
            self.game_state = "game_over"
            self.message = "Tap to try again"
            if self.score > self.best_score:
                self.best_score = self.score
                self.save_best_score()

        self._redraw()

    def _draw_filled_star(self, cx: float, cy: float, radius: float, spikes: int, color, angle: float = 0) -> None:
        Color(*color)
        verts = make_star_verts(cx, cy, radius, spikes, angle)
        idx_count = len(verts) // 4
        Mesh(vertices=verts, indices=list(range(idx_count)), mode="triangle_fan")

    def _draw_filled_circle(self, cx: float, cy: float, r: float, color) -> None:
        Color(*color)
        Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))

    def _redraw(self) -> None:
        self.canvas.clear()
        sx, sy = self.shake_offset

        with self.canvas:
            Color(*C_BG)
            Rectangle(pos=(sx, sy), size=self.size)

            for bx, by, br in self.bg_stars:
                drift = (self.distance * br * 2.5) % self.width
                Color(1, 1, 1, 0.35 + br * 0.12)
                Ellipse(pos=((bx + drift + sx) % self.width, by), size=(br, br))

            if self.flash_timer > 0:
                Color(1, 1, 1, 0.08)
                Rectangle(pos=(sx, sy), size=self.size)

            for obj in self.objects:
                ox, oy, r = obj.x + sx, obj.y + sy, obj.radius
                if obj.kind == "bomb":
                    self._draw_filled_circle(ox, oy, r, C_BOMB)
                    Color(0.7, 0.7, 0.7, 1)
                    Ellipse(pos=(ox + 7, oy + 4), size=(8, 8))
                    Color(1, 1, 1, 0.15)
                    Ellipse(pos=(ox - r + 2, oy - r + 2), size=(r * 2 - 4, r * 2 - 4))
                elif obj.kind == "clock":
                    self._draw_filled_circle(ox, oy, r, C_CLOCK)
                    Color(0.2, 0.2, 0.3, 1)
                    Line(circle=(ox, oy, r - 4), width=3)
                    Line(points=[ox, oy, ox, oy + 9], width=3)
                    Line(points=[ox, oy, ox + 8, oy], width=3)
                elif obj.kind == "gem":
                    self._draw_filled_star(ox, oy, r, GEM_SPIKES, C_GEM, obj.angle)
                    Color(1, 1, 1, 0.25)
                    self._draw_filled_star(ox - 2, oy - 3, r * 0.35, GEM_SPIKES, C_WHITE, obj.angle)
                else:
                    self._draw_filled_star(ox, oy, r, STAR_SPIKES, C_STAR, obj.angle)
                    Color(1, 1, 1, 0.3)
                    self._draw_filled_star(ox - 2, oy - 3, r * 0.3, STAR_SPIKES, C_WHITE, obj.angle)

            px, py = self._player_x + sx, self._player_y + sy

            Color(*C_WING)
            Triangle(points=[px + 12, py + 12, px - 16, py + 3, px + 12, py - 3])
            Triangle(points=[px + self.player_w - 12, py + 12, px + self.player_w + 16, py + 3, px + self.player_w - 12, py - 3])

            Color(*C_PLAYER)
            RoundedRectangle(pos=(px, py), size=(self.player_w, self.player_h), radius=[14])
            Color(*C_WHITE)
            Line(rounded_rectangle=(px, py, self.player_w, self.player_h, 14), width=2)
            Color(1, 1, 1, 0.2)
            RoundedRectangle(pos=(px + 8, py + 3), size=(self.player_w - 30, self.player_h - 8), radius=[8])

            for ft in self.floating_texts:
                alpha = max(0, ft.life)
                Color(*ft.color[:3], ft.color[3] if len(ft.color) > 3 else 1 * alpha)
                lbl_x = ft.x - 30 + sx
                lbl_y = ft.y + sy
                RoundedRectangle(pos=(lbl_x, lbl_y), size=(60, 22), radius=[4])
                Color(0, 0, 0, 0.6 * alpha)
                Line(rounded_rectangle=(lbl_x, lbl_y, 60, 22, 4), width=1)

        self._draw_labels()

    def _draw_labels(self) -> None:
        if not hasattr(self, "score_label"):
            return
        self.score_label.text = f"Score: {self.score}"
        self.best_label.text = f"Best: {self.best_score}"
        self.level_label.text = f"Level: {self.level}"
        self.combo_label.text = f"Combo: {self.combo}"
        hps = "❤" * max(0, self.energy) + "♡" * max(0, 5 - self.energy)
        self.energy_label.text = hps

        if self.game_state == "menu":
            self.center_label.text = "SKY COLLECTOR\nTap to start"
        elif self.game_state == "game_over":
            self.center_label.text = f"GAME OVER\nScore: {self.score}\nTap to restart"
        else:
            self.center_label.text = self.message


class SkyCollectorRoot(FloatLayout):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.game = GameWidget(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.add_widget(self.game)

        kwargs = {"font_size": "22sp", "bold": True, "color": C_WHITE, "size_hint": (None, None)}
        self.score_label = Label(text="Score: 0", **kwargs)
        self.best_label = Label(text="Best: 0", font_size="17sp", bold=False, color=C_WHITE, size_hint=(None, None))
        self.level_label = Label(text="Level: 1", font_size="17sp", bold=False, color=C_WHITE, size_hint=(None, None))
        self.combo_label = Label(text="Combo: 0", font_size="17sp", bold=False, color=C_WHITE, size_hint=(None, None))
        self.energy_label = Label(text="❤❤❤❤❤", font_size="20sp", color=(0.9, 0.3, 0.3, 1), size_hint=(None, None))
        self.center_label = Label(text="SKY COLLECTOR\nTap to start", font_size="30sp", bold=True, halign="center", color=C_WHITE)
        self.center_label.size_hint = (1, None)
        self.center_label.text_size = (Window.width, None)
        self.center_label.pos_hint = {"center_x": 0.5, "center_y": 0.56}

        for lbl in [self.score_label, self.best_label, self.level_label, self.combo_label, self.energy_label, self.center_label]:
            self.add_widget(lbl)

        self.game.score_label = self.score_label
        self.game.best_label = self.best_label
        self.game.level_label = self.level_label
        self.game.combo_label = self.combo_label
        self.game.energy_label = self.energy_label
        self.game.center_label = self.center_label

        self.bind(size=self._update_layout)
        Window.bind(size=self._window_resized)
        self._update_layout()

    def _window_resized(self, *_args) -> None:
        self._update_layout()

    def _update_layout(self, *_args) -> None:
        h = self.height or Window.height
        w = self.width or Window.width
        self.score_label.pos = (18, h - 52)
        self.best_label.pos = (18, h - 82)
        self.level_label.pos = (18, h - 112)
        self.combo_label.pos = (18, h - 142)
        self.energy_label.pos = (w - 140, h - 48)
        self.center_label.text_size = (w - 40, None)


class SkyCollectorApp(App):
    def build(self):
        self.title = "Sky Collector"
        return SkyCollectorRoot()

    def on_pause(self):
        return True


if __name__ == "__main__":
    SkyCollectorApp().run()
