---
title: "{{ title | replace('\"','') | safe }}"
artist: "{{ artist | replace('\"','') | safe }}"
album_name: "{{ album_name | replace('\"','') | safe }}"
date: {{ date_added }}{% if apple_music_editorialNotes != None %}
release_date: "{{ apple_music_album_release_date }}"{% endif %}
release_id: "{{ release_id }}"
slug: "{{ slug }}"
hideSummary: true
cover:
    image: "{{ cover_filename }}"
    alt: "{{ album_name  | replace('\"','') | safe }} by {{ artist | replace('\"','') | safe  }}"
    caption: "{{ album_name  | replace('\"','') | safe }} by {{ artist  | replace('\"','') | safe }}"
additional_images:
{%- for image_url in image_urls %}
    - "{{ image_url }}"
{%- endfor %}
genres: [{% for genre in genres %}"{{ genre }}"{% if not loop.last %}, {% endif %}{% endfor %}]
styles: [{% for style in styles %}"{{ style }}"{% if not loop.last %}, {% endif %}{% endfor %}]
---

{% raw %}{{< img src="{% endraw %}{{ cover_filename }}{% raw %}" title="{% endraw %}{{ album_name  | replace('\"','') | safe }} by {{ artist | replace('\"','') | safe  }}{% raw %}" >}}{% endraw %}

<!-- section break -->

{{ track_list }}

<!-- section break -->

{% if wikipedia_summary is not none and apple_music_editorialNotes is not none -%}
    {% if wikipedia_summary|length > apple_music_editorialNotes|length -%}
        {{ wikipedia_summary }}
    {% else -%}
        {{ apple_music_editorialNotes }}
    {% endif -%}
{% elif wikipedia_summary is not none -%}
    {{ wikipedia_summary }}
{% elif apple_music_editorialNotes is not none -%}
    {{ apple_music_editorialNotes }}
{% endif -%}
<br>
{% if apple_music_album_url != None -%}
## Apple Music
{% raw %}{{< applemusic url="{% endraw %}{{ apple_music_album_url }}{% raw %}" >}}{% endraw %}
{% elif spotify -%}
## Spotify
{% raw %}{{< spotify type="album" id="{% endraw %}{{ spotify }}{% raw %}" width="100%" height="500" >}}{% endraw %}
{% endif -%}

{% if first_video_id -%}
## Videos
### {{ first_video_title }}
{% raw %}{{< youtube id="{% endraw %}{{ first_video_id }}{% raw %}" title="{% endraw %}{{ first_video_title }}{% raw %}" >}}{% endraw %}<br>
{% if additional_videos -%}
### More Videos
{% for video in additional_videos %}
- [{{ video.title }}]({{ video.url }}){% endfor %}{% endif -%}
{% endif %}

## Release Images
{% raw %}{{< imageGrid >}}{% endraw %}

## Release Information
|  Key           | Value                                                |
| ---------------| ---------------------------------------------------- |
{% if wikipedia_url -%}
| Wikipedia URL | {{ wikipedia_url }} |
{% endif -%}
{% if wikipedia_summary is not none and apple_music_editorialNotes is not none -%}
    {% if wikipedia_summary|length < apple_music_editorialNotes|length -%}
    | Wikipedia Summary | {{ wikipedia_summary|replace('\n', '<br>') }} |
    {% else -%}
    | Apple Music Summary | {{ apple_music_editorialNotes|replace('\n', '<br>') }} |
    {% endif -%}
{% elif wikipedia_summary is not none -%}
    | Wikipedia Summary | {{ wikipedia_summary|replace('\n', '<br>') }} |
{% elif apple_music_editorialNotes is not none -%}
    | Apple Music Summary | {{ apple_music_editorialNotes|replace('\n', '<br>') }} |
{% endif -%}
| Release Year   | {{ release_date }}                                   |
| Format         | {{ release_formats }} |
| Label          | {{ label }} |
| Catalog Number | {{ catalog_number }} |
{% if notes -%}
| Notes | {{ notes|replace('\n', '<br>') }} |
{% endif -%}
| Discogs URL    | [{{ artist }} - {{ album_name }}]({{ release_url }}) |
