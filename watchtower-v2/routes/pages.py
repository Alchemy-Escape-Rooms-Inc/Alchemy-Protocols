"""
WatchTower V2 Page Routes
"""
from flask import Blueprint, render_template, abort, redirect
import config
from models.grimoire_loader import get_all_sections, get_device_index, get_device_section

pages = Blueprint("pages", __name__)


@pages.route("/")
def dashboard():
    return render_template("dashboard.html")


@pages.route("/game")
def game_control():
    return render_template("game_control.html")


@pages.route("/mqtt")
def mqtt_feed():
    return render_template("mqtt_feed.html")


@pages.route("/library")
def library():
    grimoire = get_all_sections()
    devices = get_device_index()
    return render_template(
        "library.html",
        gravity_topics=config.GRAVITY_GAMES_TOPICS,
        grimoire=grimoire,
        devices=devices,
    )


@pages.route("/library/device/<slug>")
def device_page(slug):
    device = get_device_section(slug)
    if device is None:
        abort(404)
    return render_template("device_page.html", device=device)


# Power (smart switches) lives inside Game Control; keep the old URL working.
@pages.route("/power")
def power():
    return redirect("/game")


@pages.route("/debug")
def debug_log():
    return render_template("debug_log.html")


# Alyssa (phone receptionist) call history — pulled live from ElevenLabs.
@pages.route("/calls")
def alyssa_calls():
    return render_template("calls.html")


# Tink (ex-Smee) lives in the floating widget on every page now.
@pages.route("/chat")
def chat():
    return redirect("/")
