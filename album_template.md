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
genres: {{ genres }}
styles: {{ styles }}
---

## Tracklisting
{{ track_list }}

## Videos
{% raw %}    {{< youtube id="{{ first_video_id }}" title="{{ first_video_title }}" >}}{% endraw %}
{% if additional_videos %}{% for video in additional_videos %}
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