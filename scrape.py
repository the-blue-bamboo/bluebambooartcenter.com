#!/usr/bin/env python3
"""
Scrape upcoming events from Blue Bamboo Center for the Arts
and generate a simple black-on-white HTML email blast.
"""

import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://bluebambooartcenter.com/event-calendar"


def parse_events_from_soup(soup):
    """Parse event-detail blocks from a BeautifulSoup object."""
    events = []
    for detail in soup.select("div.event-detail"):
        event = {}

        # Unique key for deduplication
        event_id = detail.get("data-event-id", "")
        occurrence_id = detail.get("data-occurrence-id", "")
        event["uid"] = f"{event_id}-{occurrence_id}"

        # Title & link
        title_tag = detail.select_one(".event-title a")
        if title_tag:
            event["title"] = title_tag.get_text(strip=True)
            event["link"] = title_tag["href"]
        else:
            continue

        # Image
        img_tag = detail.select_one(".event-image img")
        if img_tag and img_tag.get("src"):
            src = img_tag["src"]
            if src.startswith("//"):
                src = "https:" + src
            # Use the larger image (swap 200 -> 600 in base64 resize param)
            src = src.replace("MjAw", "NjAw")
            event["image"] = src

        # Date/time (use the short date version)
        date_short = detail.select_one(".date-short")
        if date_short:
            event["datetime"] = date_short.get_text(" ", strip=True)
        else:
            date_long = detail.select_one(".date-long")
            if date_long:
                event["datetime"] = date_long.get_text(" ", strip=True)

        # Description
        notes = detail.select_one(".event-notes")
        if notes:
            paragraphs = []
            for p in notes.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
            event["description"] = "\n\n".join(paragraphs)

        # Price
        price_tag = detail.select_one(".price")
        if price_tag:
            event["price"] = price_tag.get_text(strip=True)

        # Ticket link
        ticket_tag = detail.select_one("a.tickets")
        if ticket_tag and ticket_tag.get("href"):
            event["ticket_url"] = ticket_tag["href"]

        events.append(event)

    return events


def scrape_events():
    """Fetch all pages of events, deduplicating by occurrence ID."""
    seen = set()
    all_events = []
    page = 1

    while True:
        params = {"calendar_page": page} if page > 1 else {}
        print(f"  Fetching page {page}…")
        resp = requests.get(URL, params=params, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        page_events = parse_events_from_soup(soup)
        if not page_events:
            break

        new_count = 0
        for ev in page_events:
            if ev["uid"] not in seen:
                seen.add(ev["uid"])
                all_events.append(ev)
                new_count += 1

        print(f"    {len(page_events)} events on page, {new_count} new")

        # Stop if no new events were found (we've looped back)
        if new_count == 0:
            break

        # Check if there's a next page link
        next_link = soup.select_one('a[href*="calendar_page="]')
        has_next = False
        if next_link:
            href = next_link.get("href", "")
            if f"calendar_page={page + 1}" in href:
                has_next = True
        # Also continue if page 1 (always try page 2)
        if not has_next and page > 1:
            break

        page += 1

    return all_events


def filter_upcoming(events):
    """Keep only events that haven't happened yet."""
    today = datetime.now().date()
    upcoming = []
    for ev in events:
        dt_str = ev.get("datetime", "")
        # Parse date like "Fri, Mar 20 @ 8:00PM ..." -> extract "Mar 20"
        m = re.search(r"(\w{3}),\s+(\w{3})\s+(\d{1,2})\s+@", dt_str)
        if m:
            month_str, day_str = m.group(2), m.group(3)
            try:
                event_date = datetime.strptime(
                    f"{month_str} {day_str} {today.year}", "%b %d %Y"
                ).date()
                # If the parsed date is far in the past, it might be next year
                if event_date < today.replace(month=1, day=1):
                    event_date = event_date.replace(year=today.year + 1)
                if event_date >= today:
                    upcoming.append(ev)
                continue
            except ValueError:
                pass
        # If we can't parse the date, include it anyway
        upcoming.append(ev)
    return upcoming


def build_html(events):
    event_blocks = []
    for ev in events:
        img_html = ""
        if ev.get("image"):
            img_html = (
                f'<img src="{ev["image"]}" alt="{ev["title"]}" '
                f'style="width:100%;height:auto;display:block;'
                f'border-radius:8px 8px 0 0;" />'
            )

        title_html = f'<a href="{ev["link"]}" style="color:#111;text-decoration:underline;text-underline-offset:2px;">{ev["title"]}</a>'

        datetime_html = ""
        if ev.get("datetime"):
            datetime_html = (
                f'<p style="margin:0 0 14px 0;font-size:13px;color:#666;'
                f'letter-spacing:0.3px;text-transform:uppercase;">'
                f'{ev["datetime"]}</p>'
            )

        desc_html = ""
        if ev.get("description"):
            paragraphs = ev["description"].split("\n\n")
            desc_parts = []
            for p in paragraphs:
                desc_parts.append(
                    f'<p style="margin:0 0 10px 0;font-size:15px;'
                    f'line-height:1.6;color:#333;">{p}</p>'
                )
            desc_html = "".join(desc_parts)

        price_html = ""
        if ev.get("price"):
            price_html = (
                f'<p style="margin:12px 0 0 0;font-size:14px;color:#444;'
                f'font-style:italic;">'
                f'{ev["price"]}</p>'
            )

        buttons = []
        if ev.get("ticket_url"):
            buttons.append(
                f'<a href="{ev["ticket_url"]}" '
                f'style="display:inline-block;padding:10px 24px;'
                f'background-color:#111;color:#fff;font-size:14px;'
                f'font-weight:600;text-decoration:none;border-radius:6px;'
                f'margin-right:10px;">Get Tickets</a>'
            )
        buttons.append(
            f'<a href="{ev["link"]}" '
            f'style="display:inline-block;padding:10px 24px;'
            f'background-color:#fff;color:#111;font-size:14px;'
            f'font-weight:600;text-decoration:none;border-radius:6px;'
            f'border:1px solid #ccc;">Share</a>'
        )
        buttons_html = (
            f'<p style="margin:18px 0 0 0;">{"".join(buttons)}</p>'
        )

        block = f"""
    <tr><td style="padding:0 0 20px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="border-radius:8px;overflow:hidden;border:1px solid #e8e8e8;">
        <tr><td>
          {img_html}
        </td></tr>
        <tr><td style="padding:20px 24px 24px 24px;">
          <h2 style="margin:0 0 8px 0;font-size:22px;font-weight:700;line-height:1.3;">
            {title_html}
          </h2>
          {datetime_html}
          {desc_html}
          {price_html}
          {buttons_html}
        </td></tr>
      </table>
    </td></tr>"""
        event_blocks.append(block)

    events_html = "\n".join(event_blocks)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Blue Bamboo Center for the Arts — Upcoming Events</title>
</head>
<body style="margin:0;padding:0;background-color:#f5f5f5;color:#000000;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="max-width:640px;margin:0 auto;padding:30px 20px;">
    <tr><td style="text-align:center;padding:10px 0 40px 0;">
      <h1 style="margin:0;font-size:28px;color:#111;font-weight:800;letter-spacing:-0.5px;">
        Blue Bamboo Center for the Arts
      </h1>
      <p style="margin:8px 0 0 0;font-size:15px;color:#888;font-weight:400;">
        Upcoming Events
      </p>
    </td></tr>
{events_html}
    <tr><td style="padding:40px 0 20px 0;text-align:center;
                    font-size:13px;color:#999;line-height:1.6;">
      <p style="margin:0 0 4px 0;font-weight:600;color:#666;">Blue Bamboo Center for the Arts</p>
      460 E New England Ave, Winter Park, FL 32789<br>
      407-636-9951<br><br>
      <a href="https://bluebambooartcenter.com/" style="color:#111;text-decoration:underline;text-underline-offset:2px;">
        bluebambooartcenter.com</a>
    </td></tr>
  </table>
</body>
</html>"""


def main():
    print("Scraping events from Blue Bamboo…")
    events = scrape_events()
    print(f"  Found {len(events)} total events")

    events = filter_upcoming(events)
    print(f"  {len(events)} upcoming events after filtering")

    if not events:
        print("No upcoming events found.")
        sys.exit(0)

    html = build_html(events)

    outfile = "output.html"
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Written to {outfile}")


if __name__ == "__main__":
    main()
