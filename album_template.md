---
title: "{{ title }}"
artist: "{{ artist }}"
album_name: "{{ album_name }}"
date: {{ date_added }}
release_id: "{{ release_id }}"
slug: "{{ slug }}"
hideSummary: true
cover:
    image: "{{ cover_filename }}"
    alt: "{{ album_name }} by {{ artist }}"
    caption: "{{ album_name }} by {{ artist }}"
genres: [{% for genre in genres %}"{{ genre }}"{% if not loop.last %}, {% endif %}{% endfor %}]
styles: [{% for style in styles %}"{{ style }}"{% if not loop.last %}, {% endif %}{% endfor %}]
---

## Tracklisting
{{ track_list }}

{% if spotify %}
## Spotify
{% raw %}{{< spotify type="album" id="{{ spotify }}" width="100%" height="500" >}}{% endraw %}
{% endif %}

## Videos
{% raw %}{{< youtube id="{{ first_video_id }}" title="{{ first_video_title }}" >}}{% endraw %}{% if additional_videos %}{% for video in additional_videos %}
- [{{ video.title }}]({{ video.url }}){% endfor %}{% endif %}

## Notes
| Notes          |             |
| ---------------| ----------- |
| Release Year   | {{ release_date }} |
| Discogs Link   | [{{ artist }} - {{ album_name }}]({{ release_url }}) |
| Label          | {{ label }} |
| Format         | {{ release_formats }} |
| Catalog Number | {{ catalog_number }} |
{% if notes %}
{{ notes }}
{% endif %}