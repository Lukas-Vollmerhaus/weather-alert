#!/home/lukas/miniconda3/envs/weather-alert/bin/python

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.colors as mcolors
import matplotlib.cm as mcm
import numpy as np
import pandas as pd
from datetime import datetime
import configparser
import smtplib
import syslog
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email import encoders
from model_data_fetch import load_locations, fetch_forecast, MODEL_CONFIG
from weather_fitness import evaluate_weather_fitness, SEASON

OUTPUT_PNG  = "/tmp/weather_alert.png"
SUMMARY_PNG = "/tmp/weather_alert_summary.png"

EMAIL_CONF        = "/usr/local/src/weather-alert/email.conf"
LOCATIONS_CONF    = "/usr/local/src/weather-alert/locations.conf"
FITNESS_CONF_PATH = "/usr/local/src/weather-alert/weather_fitness.conf"

RESET = "\033[0m"

# Colour assigned to each model in plots
MODEL_COLORS = {
    "GDPS": "#1f77b4",
    "RDPS": "#ff7f0e",
    "GFS":  "#2ca02c",
    "NAM":  "#d62728",
}


def fetch_all_data():
    """
    Fetch raw hourly forecast DataFrames for every location/model combination.

    Returns:
        dict: {location_name: {model: pd.DataFrame or None}}
    """
    locations = load_locations()
    all_data = {}
    for loc in locations:
        all_data[loc.name] = {}
        for model in MODEL_CONFIG:
            syslog.syslog(syslog.LOG_INFO, f"Fetching {model} for {loc.name}")
            try:
                all_data[loc.name][model] = fetch_forecast(loc, model)
            except Exception as e:
                syslog.syslog(syslog.LOG_ERR, f"Failed to fetch {model} for {loc.name}: {e}")
                all_data[loc.name][model] = None
    return all_data


def evaluate_all(all_data):
    """
    Evaluate daily fitness scores from pre-fetched data.

    Returns:
        pd.DataFrame with columns: location, model, date, fitness_score
    """
    records = []
    for loc_name, models in all_data.items():
        for model, df in models.items():
            if df is None:
                continue
            for date, day_data in df.groupby(df["DATETIME"].dt.date):
                day_data = day_data.reset_index(drop=True)
                if len(day_data) < 2:
                    continue
                try:
                    score, top_contributor = evaluate_weather_fitness(day_data)
                except Exception as e:
                    syslog.syslog(syslog.LOG_ERR, f"Could not score {loc_name} {model} {date}: {e}")
                    continue
                daily_precip = day_data["APCP"].diff().fillna(0).sum()
                daily_high_temp = day_data["TMP"].max()
                records.append({
                    "location":        loc_name,
                    "model":           model,
                    "date":            pd.Timestamp(date),
                    "fitness_score":   score,
                    "top_contributor": top_contributor,
                    "precip_mm":       daily_precip,
                    "high_temp_c":     daily_high_temp,
                })
    return pd.DataFrame(records, columns=["location", "model", "date", "fitness_score", "top_contributor", "precip_mm", "high_temp_c"])


def score_to_color(score, min_score, max_score):
    """
    Map a fitness score to an ANSI true-color escape code on a
    green -> yellow -> orange -> red gradient.
    """
    # Gradient stops: (R, G, B)
    stops = [
        (0,   200,   0),   # green  (best)
        (255, 255,   0),   # yellow
        (255, 165,   0),   # orange
        (220,   0,   0),   # red    (worst)
    ]

    if max_score == min_score:
        t = 0.0
    else:
        t = (score - min_score) / (max_score - min_score)
    t = max(0.0, min(1.0, t))

    # Map t to a segment between two adjacent stops
    segments = len(stops) - 1
    scaled = t * segments
    i = min(int(scaled), segments - 1)
    local_t = scaled - i

    r1, g1, b1 = stops[i]
    r2, g2, b2 = stops[i + 1]
    r = int(r1 + (r2 - r1) * local_t)
    g = int(g1 + (g2 - g1) * local_t)
    b = int(b1 + (b2 - b1) * local_t)

    return f"\033[38;2;{r};{g};{b}m"

def print_calendar(results):
    """
    Print a calendar-style table for each location with fitness scores
    colored on a green-yellow-orange-red gradient.
    """
    min_score = results["fitness_score"].min()
    max_score = results["fitness_score"].max()
    print(results.keys)

    for location, loc_df in results.groupby("location"):
        print(f"\n{'='*60}")
        print(f"  {location}")
        print(f"{'='*60}")

        calendar = loc_df.pivot(index="model", columns="date", values="fitness_score")
        calendar.columns = [d.strftime("%a %b %d") for d in calendar.columns]
        calendar.index.name = "Model"

        col_width = 11
        precip_pivot = loc_df.pivot(index="model", columns="date", values="precip_mm")
        precip_pivot.columns = [d.strftime("%a %b %d") for d in precip_pivot.columns]

        contrib_pivot = loc_df.pivot(index="model", columns="date", values="top_contributor")
        contrib_pivot.columns = [d.strftime("%a %b %d") for d in contrib_pivot.columns]

        temp_pivot = loc_df.pivot(index="model", columns="date", values="high_temp_c")
        temp_pivot.columns = [d.strftime("%a %b %d") for d in temp_pivot.columns]

        _CONTRIB_SHORT = {
            "temperature":   "temp",
            "cloud":         "cloud",
            "wind":          "wind",
            "precipitation": "precip",
        }

        # Header row
        header = f"{'Model':<10}" + "".join(f"{col:>{col_width}}" for col in calendar.columns)
        print(header)

        # Data rows: fitness score + precip + top contributor beneath each model
        for model, row in calendar.iterrows():
            # Fitness score line
            line = f"{model:<10}"
            for score in row:
                if pd.isna(score):
                    line += f"{'  -  ':>{col_width}}"
                else:
                    color = score_to_color(score, min_score, max_score)
                    line += f"{color}{score:>{col_width}.1f}{RESET}"
            print(line)

            # Temperature line
            tline = f"{'  high':<10}"
            for t in temp_pivot.loc[model]:
                if pd.isna(t):
                    tline += f"{'  -  ':>{col_width}}"
                else:
                    tline += f"{f'{t:.1f}°C':>{col_width}}"
            print(tline)

            # Precip line
            pline = f"{'  precip':<10}"
            for p in precip_pivot.loc[model]:
                if pd.isna(p):
                    pline += f"{'  -  ':>{col_width}}"
                else:
                    pline += f"{'(' + f'{p:.1f}mm' + ')':>{col_width}}"
            print(pline)

            # Top contributor line
            cline = f"{'  driver':<10}"
            for c in contrib_pivot.loc[model]:
                if pd.isna(c):
                    cline += f"{'  -  ':>{col_width}}"
                else:
                    cline += f"{'[' + _CONTRIB_SHORT.get(c, c) + ']':>{col_width}}"
            print(cline)


def score_to_rgb(score, min_score, max_score):
    """Return an (R, G, B) tuple (0–1 floats) for the green→yellow→orange→red gradient."""
    stops = [
        (0.0,  0.78, 0.0),   # green
        (1.0,  1.0,  0.0),   # yellow
        (1.0,  0.65, 0.0),   # orange
        (0.86, 0.0,  0.0),   # red
    ]
    if max_score == min_score:
        t = 0.0
    else:
        t = max(0.0, min(1.0, (score - min_score) / (max_score - min_score)))
    segments = len(stops) - 1
    scaled = t * segments
    i = min(int(scaled), segments - 1)
    local_t = scaled - i
    r1, g1, b1 = stops[i]
    r2, g2, b2 = stops[i + 1]
    return (r1 + (r2 - r1) * local_t,
            g1 + (g2 - g1) * local_t,
            b1 + (b2 - b1) * local_t)


def plot_forecasts(all_data, results, path=OUTPUT_PNG):
    """
    Produce a PNG with all plots in a single column.
    Each subplot shows one variable for one location with all model lines
    overlaid, and day-column backgrounds shaded by average fitness score.
    """
    locations = list(all_data.keys())
    variables = [
        ("TMP",   "Temperature (°C)"),
        ("CLOUD", "Cloud Cover (%)"),
        ("APCP",  "Precip – cumulative (mm)"),
        ("WS",    "Wind Speed (km/h)"),
    ]

    min_score = results["fitness_score"].min()
    max_score = results["fitness_score"].max()

    # Pre-compute mean fitness score per (location, date) across models
    daily_scores = (
        results.groupby(["location", "date"])["fitness_score"]
        .mean()
        .reset_index()
    )

    n_locs  = len(locations)
    n_vars  = len(variables)
    n_plots = n_locs * n_vars
    fig, axes = plt.subplots(
        n_plots, 1,
        figsize=(10, n_plots * 3),
        sharex=False,
    )
    fig.suptitle(f"Weather Alert Details by Location and Model — {SEASON.title()}", fontsize=14, fontweight="bold", y=0.995)

    for row, loc_name in enumerate(locations):
        loc_scores = daily_scores[daily_scores["location"] == loc_name].sort_values("date")

        for col, (var, ylabel) in enumerate(variables):
            ax = axes[row * n_vars + col]

            # Shade each day column with its fitness colour before drawing lines
            for _, score_row in loc_scores.iterrows():
                day_start = score_row["date"]
                day_end   = day_start + pd.Timedelta(days=1)
                rgb = score_to_rgb(score_row["fitness_score"], min_score, max_score)
                ax.axvspan(day_start, day_end, color=rgb, alpha=0.25, linewidth=0)

            for model, df in all_data[loc_name].items():
                if df is None:
                    continue
                ax.plot(
                    df["DATETIME"], df[var],
                    label=model,
                    color=MODEL_COLORS[model],
                    linewidth=1.2,
                )

            # Variable name in top-right corner of each plot
            ax.text(0.98, 0.95, ylabel, transform=ax.transAxes,
                    ha="right", va="top", fontsize=8, fontstyle="italic",
                    color="black")
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=90, ha="right", fontsize=7)
            ax.tick_params(axis="y", labelsize=7)
            ax.grid(True, linestyle="--", alpha=0.3)

    # Leave left margin for location labels, small top margin for legends
    plt.tight_layout(rect=[0.05, 0.01, 1, 0.97])

    fig.canvas.draw()

    # Fitness score colorbar — horizontal, top right, slim bar
    gradient_stops = [
        (0.0,  0.78, 0.0),
        (1.0,  1.0,  0.0),
        (1.0,  0.65, 0.0),
        (0.86, 0.0,  0.0),
    ]
    fitness_cmap = mcolors.LinearSegmentedColormap.from_list(
        "fitness", gradient_stops, N=256
    )
    cbar_ax = fig.add_axes([0.5, 0.979, 0.46, 0.003])
    cb = fig.colorbar(
        mcm.ScalarMappable(
            norm=mcolors.Normalize(vmin=min_score, vmax=max_score),
            cmap=fitness_cmap,
        ),
        cax=cbar_ax,
        orientation="horizontal",
    )
    cb.set_label("Fitness Score (lower = better)", fontsize=8, labelpad=4)
    cb.set_ticks(np.linspace(min_score, max_score, 5))
    cb.ax.tick_params(labelsize=7)

    # Model legend — horizontal, top right, above colorbar
    handles = [
        plt.Line2D([0], [0], color=MODEL_COLORS[m], linewidth=1.5, label=m)
        for m in MODEL_CONFIG
    ]
    fig.legend(handles=handles, loc="upper right", ncol=len(MODEL_CONFIG),
               fontsize=9, frameon=True, bbox_to_anchor=(0.99, 0.973))

    # Add alternating background bands and location labels
    fig.canvas.draw()
    band_colors = ["#d0d0d0", "#ffffff"]
    for row, loc_name in enumerate(locations):
        top_ax    = axes[row * n_vars]
        bottom_ax = axes[row * n_vars + n_vars - 1]
        top_pos    = top_ax.get_position()
        bottom_pos = bottom_ax.get_position()

        # Span from bottom of last subplot to top of first subplot in this group
        band_y      = bottom_pos.y0
        band_height = top_pos.y1 - bottom_pos.y0
        fig.add_artist(plt.Rectangle(
            (0, band_y), 1, band_height,
            transform=fig.transFigure,
            color=band_colors[row % 2],
            zorder=0,
        ))

        center_y = (top_pos.y0 + top_pos.y1 + bottom_pos.y0 + bottom_pos.y1) / 4
        fig.text(0.01, center_y, loc_name,
                 ha="center", va="center", rotation=90,
                 fontsize=10, fontweight="bold", zorder=1)
    fig.text(0.5, 0.002, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             ha="center", va="bottom", fontsize=7, color="grey")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    syslog.syslog(syslog.LOG_INFO, f"Saved detail plot to {path}")


def plot_fitness_summary(results, path=SUMMARY_PNG):
    """
    Produce a calendar-style heatmap PNG: rows = locations, columns = dates,
    each cell shaded by the mean fitness score across models.
    """
   
    gradient_stops = [
        (0.0,  0.78, 0.0),
        (1.0,  1.0,  0.0),
        (1.0,  0.65, 0.0),
        (0.86, 0.0,  0.0),
    ]
  
    # Pivot to (location × date) matrix of mean scores
    daily_avg = (
        results.groupby(["location", "date"])["fitness_score"]
        .mean()
        .reset_index()
    )

    # Most common top contributor across models for each (location, date)
    daily_contrib = (
        results.groupby(["location", "date"])["top_contributor"]
        .agg(lambda x: x.mode().iloc[0])
        .reset_index()
    )

    min_score = daily_avg["fitness_score"].min()
    max_score = daily_avg["fitness_score"].max()

    fitness_cmap = mcolors.LinearSegmentedColormap.from_list(
        "fitness", gradient_stops, N=256
    )
    norm = mcolors.Normalize(vmin=min_score, vmax=max_score)

    _CONTRIB_SHORT = {
        "temperature":   "temp",
        "cloud":         "cloud",
        "wind":          "wind",
        "precipitation": "precip",
    }

    pivot = daily_avg.pivot(index="location", columns="date", values="fitness_score")
    contrib_pivot = daily_contrib.pivot(index="location", columns="date", values="top_contributor")
    dates     = pivot.columns
    locations = pivot.index.tolist()
    n_locs = len(locations)
    n_days = len(dates)

    cell_w, cell_h = 1.0, 1.0
    fig_w = max(10, n_days * 0.9 + 3)
    fig_h = n_locs * 1 + 0.6
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_xlim(0, n_days)
    ax.set_ylim(0, n_locs)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.suptitle(f"Weather Quality by Location — {SEASON.title()}", fontsize=18,
                 fontweight="bold", y=0.995)

    for r, loc_name in enumerate(locations):
        y = n_locs - r - 1  # top-to-bottom
        # Row label
        ax.text(-0.2, y + 0.5, loc_name, ha="right", va="center",
                fontsize=13, fontweight="bold")
        for c, date in enumerate(dates):
            score = pivot.loc[loc_name, date]
            color = fitness_cmap(norm(score)) if not pd.isna(score) else "#cccccc"
            rect = plt.Rectangle((c, y), cell_w, cell_h,
                                  facecolor=color, edgecolor="white", linewidth=1.5)
            ax.add_patch(rect)
            if not pd.isna(score):
                ax.text(c + 0.5, y + 0.62, f"{score:.1f}",
                        ha="center", va="center", fontsize=11, color="black")
                contrib = contrib_pivot.loc[loc_name, date] if (
                    loc_name in contrib_pivot.index and date in contrib_pivot.columns
                ) else None
                if contrib and not pd.isna(contrib):
                    ax.text(c + 0.5, y + 0.28, _CONTRIB_SHORT.get(contrib, contrib),
                            ha="center", va="center", fontsize=8, color="#333333")

    # Column date labels + weekend highlight
    for c, date in enumerate(dates):
        ax.text(c + 0.5, n_locs + 0.1,
                pd.Timestamp(date).strftime("%a\n%b %d"),
                ha="center", va="bottom", fontsize=10)
        if pd.Timestamp(date).dayofweek >= 5:  # 5=Saturday, 6=Sunday
            ax.add_patch(plt.Rectangle((c, 0), cell_w, n_locs,
                                       facecolor="none", edgecolor="green",
                                       linewidth=2.5, zorder=3))

    plt.tight_layout(rect=[0, 0.01, 0.91, 0.97])

    # Colorbar — added after tight_layout to avoid UserWarning
    cbar_ax = fig.add_axes([0.92, 0.25, 0.02, 0.45])
    cb = fig.colorbar(mcm.ScalarMappable(norm=norm, cmap=fitness_cmap),
                      cax=cbar_ax, orientation="vertical")
    cb.set_label("Weather Quality\n(lower = better)", fontsize=11)
    cb.set_ticks(np.linspace(min_score, max_score, 5))
    cb.ax.tick_params(labelsize=10)
    fig.text(0.5, 0.002, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             ha="center", va="bottom", fontsize=10, color="grey")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    syslog.syslog(syslog.LOG_INFO, f"Saved summary plot to {path}")


def send_images(summary_png, detail_png, path=EMAIL_CONF):
    """
    Send the weather quality summary image inline in the email body,
    with the detail plot and conf files attached.
    """
    cfg = configparser.ConfigParser()
    cfg.read(path)

    host       = cfg.get("smtp", "host")
    port       = cfg.getint("smtp", "port")
    username   = cfg.get("smtp", "username")
    password   = cfg.get("smtp", "password")
    recipients = [r.strip() for r in cfg.get("contacts", "recipients").splitlines() if r.strip()]

    subject = f"Weather Quality — {datetime.now().strftime('%Y-%m-%d')}"

    body_html = """\
<p>Here's your daily weather quality update! If you want to change locations, fitness parameters
or reduce/stop these emails please contact your friendly neighborhood Luke</p>
<br>
<img src="cid:summary_image" width="50%">
"""

    for recipient in recipients:
        msg = MIMEMultipart("related")
        msg["From"]    = username
        msg["To"]      = recipient
        msg["Subject"] = subject

        # HTML body with inline summary image
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_html, "html"))
        msg.attach(alt)

        # Inline summary image
        with open(summary_png, "rb") as f:
            img = MIMEImage(f.read())
        img.add_header("Content-ID", "<summary_image>")
        img.add_header("Content-Disposition", "inline")
        msg.attach(img)

        # Attachments: detail plot and conf files
        for attach_path in [detail_png, LOCATIONS_CONF, FITNESS_CONF_PATH]:
            with open(attach_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                            f"attachment; filename={attach_path.split('/')[-1]}")
            msg.attach(part)

        try:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(username, password)
                server.sendmail(username, recipient, msg.as_string())
            syslog.syslog(syslog.LOG_INFO, f"Email sent to {recipient}")
        except Exception as e:
            syslog.syslog(syslog.LOG_ERR, f"Failed to send email to {recipient}: {e}")


if __name__ == "__main__":
    all_data = fetch_all_data()
    results  = evaluate_all(all_data)
    #print_calendar(results)
    plot_forecasts(all_data, results)
    plot_fitness_summary(results)
    send_images(SUMMARY_PNG, OUTPUT_PNG)
