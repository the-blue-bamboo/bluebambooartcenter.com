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
        parts = []

        # Image
        if ev.get("image"):
            parts.append(
                f'<figure class="image justify_center size_l">\n'
                f'    <a class="no-pjax" href="{ev["link"]}">'
                f'<img src="{ev["image"]}" alt="{ev["title"]}"></a>\n'
                f'</figure>'
            )

        # Title
        parts.append(
            f'<p>\n'
            f'    <span class="text-huge"><strong>'
            f'<a class="no-pjax" href="{ev["link"]}">{ev["title"]}</a>'
            f'</strong></span>\n'
            f'</p>'
        )

        # Date/time
        if ev.get("datetime"):
            parts.append(
                f'<p>\n'
                f'    <span class="text-big">{ev["datetime"]}</span>\n'
                f'</p>'
            )

        # Description
        if ev.get("description"):
            for p in ev["description"].split("\n\n"):
                if p:
                    parts.append(f'<p>\n    {p}\n</p>')

        # Price
        if ev.get("price"):
            parts.append(
                f'<p>\n'
                f'    <i>{ev["price"]}</i>\n'
                f'</p>'
            )

        # Ticket link
        if ev.get("ticket_url"):
            parts.append(
                f'<p>\n'
                f'    <span class="text-big"><strong>'
                f'<a class="no-pjax" href="{ev["ticket_url"]}">Get Tickets</a>'
                f'</strong></span>\n'
                f'</p>'
            )

        parts.append('<hr>')

        event_blocks.append("\n".join(parts))

    events_html = "\n".join(event_blocks)

    template = r"""<style>
  figure.table { margin: 0 !important; display: block !important; }
</style>
<figure class="image justify_center size_l">
    <a class="no-pjax" href="https://bluebambooartcenter.com/"><img style="aspect-ratio:1076/602;" src="https://images.zoogletools.com/s:bzglfiles/u/181211/80b196a5c6e91f35bf04f1c2cd3c5b316ba89c28/original/blue-bamboo-logo.png/!!/meta:eyJzcmNCdWNrZXQiOiJiemdsZmlsZXMifQ==" alt="Blue Bamboo Logo which links to the website." width="1076" height="602"></a>
</figure>
<p>
    &nbsp;
</p>
EVENTS_PLACEHOLDER
<p>
    <strong>Bamboo Center For the Arts</strong>&nbsp;is a registered 501(c)(3), NON-PROFIT, charitable corporation. Registration #: CH46010
</p>
<p style="text-align:center;">
    <span class="text-huge" style="color:rgb(0,0,0);">The Future is at the Blue Bamboo!</span>
</p>
<p style="text-align:center;">
    <span class="text-huge" style="color:rgb(0,0,0);">Your Music Community&nbsp;</span>
</p>
<p>
    <span class="text-big" style="color:rgb(0,0,0);"><i>Your attendance and your gift directly supports:</i></span>
</p>
<p>
    <span style="color:rgb(0,0,0);">🎶</span><span class="text-big" style="color:rgb(0,0,0);"> The Encore Room is open NOW - 184 seats!</span>
</p>
<p>
    <span style="color:rgb(0,0,0);">🎶</span><span class="text-big" style="color:rgb(0,0,0);"> The Bravo Room is open soon - 60 seats!</span>
</p>
<p>
    <span style="color:rgb(0,0,0);">🎶 </span><span class="text-big" style="color:rgb(0,0,0);">Spaces for artists to create and connect</span>
</p>
<p>
    <span style="color:rgb(0,0,0);">🎶 </span><span class="text-big" style="color:rgb(0,0,0);">Outdoor performances for the whole community</span>
</p>
<p>
    &nbsp;
</p>
<p>
    <span class="text-big" style="color:rgb(0,0,0);">Help us expand and grow. . . .</span>
</p>
<p>
    <span class="text-big" style="color:rgb(0,0,0);">Your contributions are welcome - </span><a class="no-pjax" href="https://checkout.square.site/merchant/8Q64QYG9C36EP/checkout/H3B5BSF63GIZQGJIX4YARSTW" data-link-type="url"><span class="text-big" style="color:rgb(0,0,0);">DONATE</span></a><span class="text-big" style="color:rgb(0,0,0);">.</span><span style="color:rgb(0,0,0);">&nbsp;</span>
</p>
<p>
    <span style="color:rgb(0,0,0);">For more information on how you can be a part of this music community, contact us at: info@bluebambooartcenter.com.</span>
</p>
<p>
    &nbsp;
</p>
<figure class="image justify_center size_l">
    <img style="aspect-ratio:1000/1333;" src="//images.zoogletools.com/s:bzglfiles/u/181211/38308d6a3ba057f4ffa4341c98c2c7810243c683/original/blue-bamboo-gets-new-signage.jpg/!!/meta:eyJzcmNCdWNrZXQiOiJiemdsZmlsZXMifQ==" width="1000" height="1333">
</figure>
<p>
    &nbsp;
</p>
<p>
    &nbsp;
</p>
<p>
    &nbsp;
</p>
<hr>
<p>
    <span style="color:hsl(0,0%,0%);">Check out our new sponsor -</span>
</p>
<p>
    <span class="text-big">&nbsp;</span><a class="no-pjax" href="https://www.floridasmoothjazz.com" data-link-type="url"><span class="text-big">Floridasmoothjazz.com</span></a><span class="text-big">&nbsp;</span>
</p>
<hr>
<p>
    <span class="text-big"><strong>Support</strong></span>
</p>
<p>
    Blue Bamboo Center for the Arts is sponsored in part by United Arts of Central Florida, State of Florida, Department of State, Division of Arts and Culture, the Florida Council on Arts and Culture, the National Endowment for the Arts, Orange County Government Florida Arts &amp; Cultural Affairs, and the City of Winter Park, Florida.
</p>
<p>
    &nbsp;
</p>
<p>
    &nbsp;
</p>
<p>
    &nbsp;
</p>
<figure class="image justify_left size_s">
    <img src="https://images.zoogletools.com/u/181211/53391deef9416fff3889e31db6428763f7c1d774/original/city-of-winter-park-logo.png/!!/meta:eyJzcmNCdWNrZXQiOiJiemdsZmlsZXMifQ==/b:W1sic2l6ZSIsInNtYWxsIl1d.png">
</figure>
<figure class="image justify_inline size_s">
    <img src="https://images.zoogletools.com/s:bzglfiles/u/181211/bdc6195dc4c61377c30608c84579e019b20b2eb7/original/florida-arts-and-culture-logo-vertical-square.png/!!/meta:eyJzcmNCdWNrZXQiOiJiemdsZmlsZXMifQ==/b:W1sic2l6ZSIsInNtYWxsIl1d.png" alt="">
</figure>
<figure class="image justify_inline size_s">
    <img src="https://images.zoogletools.com/u/181211/9ff4c260bef25bbc93adb23f829edcb1d26729cd/original/orange-county-arts-cultural-affairs.jpg/!!/meta:eyJzcmNCdWNrZXQiOiJiemdsZmlsZXMifQ==/b:W1sic2l6ZSIsInNtYWxsIl1d.jpg">
</figure>
<figure class="image justify_inline size_s">
    <img src="//images.zoogletools.com/s:bzglfiles/u/181211/7964eccea831e6cd95d6bd6975c3ba7b3b9be9ce/original/united-arts-central-florida.webp/!!/meta:eyJzcmNCdWNrZXQiOiJiemdsZmlsZXMifQ==" height="870">
</figure>
<p>
    &nbsp;
</p>
<p>
    We're also proud to partner with these non-profit organizations:
</p>
<p>
    &nbsp;
</p>
<figure class="image justify_center size_m">
    <img src="https://images.zoogletools.com/s:bzglfiles/u/181211/eb5281017193b4fcaa433e776d5c2f49a2a10ff5/original/pam-logo-retina-442x146-1920w.png" height="146">
</figure>
<p>
    &nbsp;&nbsp;
</p>
<p style="text-align:center;">
    <span class="text-big"><i><strong>Sincere thanks to our current "Hang" sponsors:</strong></i></span>
</p>
<figure class="table">
    <table>
        <tbody>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Gary Lambert Salon (2x)</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Epoch Residential</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>FK Architecture</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Frank Santos</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Grafton Wealth Advisors</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Philip Tiedtke</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>S &amp; W Kitchens</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Irventu</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Mike and Claire Jacobs</strong></span>
                    </p>
                </td>
            </tr>
            <tr>
                <td>
                    <p style="text-align:center;">
                        <span class="text-big"><strong>Nicki Wise</strong></span>
                    </p>
                </td>
            </tr>
        </tbody>
    </table>
</figure>
<p>
    &nbsp;
</p>
<hr>
<p>
    <span class="text-big"><strong>Other information</strong></span>
</p>
<p>
    <strong>Please subscribe to our YouTube channel:&nbsp;</strong><a class="no-pjax" href="https://www.youtube.com/c/BlueBambooMusic/videos" target="_blank" data-link-type="url" contents="Click here to see shows on our YouTube channel."><strong>Click here to see shows on our YouTube channel.</strong></a><strong>&nbsp;</strong>
</p>
<hr>
<p>
    <span class="text-big"><span><strong>Show alerts:</strong></span></span>
</p>
<p>
    If you know of others you'd like to add to this email list, please send an email to <span>info@bluebambooartcenter.com</span>
</p>
<p>
    Visit <a class="no-pjax" href="https://bluebambooartcenter.com/home" target="_blank" data-link-type="page" data-link-label="Home" contents="bluebambooartcenter.com">bluebambooartcenter.com</a> for updates.
</p>
<hr>
<p>
    BLUE BAMBOO CENTER FOR THE ARTS IS A REGISTERED 501(C)(3) CHARITABLE ORGANIZATION. <span style="color:hsl(0,0%,0%);">A COPY OF THE OFFICIAL REGISTRATION AND FINANCIAL INFORMATION MAY BE OBTAINED FROM THE DIVISION OF CONSUMER SERVICES BY CALLING TOLL-FREE 1-800-HELP-FLA OR ONLINE AT </span><a class="no-pjax" href="http://www.floridaconsumerhelp.com/"><span style="color:hsl(0,0%,0%);">www.FloridaConsumerHelp.com</span></a><span style="color:hsl(0,0%,0%);">, REGISTRATION DOES NOT IMPLY ENDORSEMENT, APPROVAL, OR RECOMMENDATION BY THE STATE. REGISTRATION #: CH46010</span>
</p>"""

    return template.replace("EVENTS_PLACEHOLDER", events_html)


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

    outfile = "index.html"
    with open(outfile, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Written to {outfile}")


if __name__ == "__main__":
    main()
