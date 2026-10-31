# Fetches a random comic cover from Metron and displays it on Inky Impression.
#
# Usage:
#   load("comic_display.be")
#   comic_display.start("METRON_USERNAME", "METRON_PASSWORD", "Batman")
#
# The search term is optional and defaults to "batman".

import webclient
import path
import tasmota
import json

var metron_api = "https://metron.cloud/api/issue/"
var comic_source_path = "/metron_comic.jpg"
var comic_download_path = "/metron_comic.download"
var comic_backup_path = "/metron_comic.backup"
var comic_dithered_path = "/metron_comic_dithered.jpg"

def metron_get_json(url, username, password)
  var wc = webclient()
  wc.set_auth(username, password)
  wc.begin(url)
  var status = wc.GET()
  if status != 200
    wc.close()
    raise "network_error", "Metron API returned HTTP " + str(status)
  end

  var response = wc.get_string()
  if response == nil || size(response) == 0
    raise "network_error", "Metron API returned an empty response"
  end

  var data = json.load(response)
  if data == nil
    raise "value_error", "Could not parse Metron API response"
  end
  return data
end

def metron_get_cover_url(issue_detail)
  # Mokkari exposes this field as a string. Accept common nested API shapes too.
  for field : ["image", "cover", "cover_image", "cover_url", "image_url"]
    var value = issue_detail[field]
    if value != nil
      if type(value) == "string" && size(value) > 0
        return value
      end
      if type(value) == "map"
        for nested_field : ["original_url", "image_url", "url"]
          var nested_value = value[nested_field]
          if type(nested_value) == "string" && size(nested_value) > 0
            return nested_value
          end
        end
      end
    end
  end
  return nil
end

def metron_download_cover(username, password, series_name, output_path)
  print("Searching Metron for: " + series_name)

  var wc = webclient()
  var encoded_series = wc.url_encode(series_name)
  var search_url = metron_api + "?series_name=" + encoded_series
  var search_data = metron_get_json(search_url, username, password)
  var results = search_data["results"]
  if results == nil || size(results) == 0
    raise "value_error", "No Metron issues found for: " + series_name
  end

  # Select one result from the first API page, matching the reference script.
  var issue_index = int(tasmota.millis() % size(results))
  var issue = results[issue_index]
  if issue["id"] == nil
    raise "value_error", "Metron issue result has no ID"
  end

  var issue_name = issue["issue_name"]
  if issue_name != nil
    print("Fetching cover for: " + str(issue_name))
  end
  var issue_url = metron_api + str(issue["id"]) + "/"
  var issue_detail_data = metron_get_json(issue_url, username, password)
  var issue_detail = issue_detail_data["results"]
  if issue_detail == nil
    issue_detail = issue_detail_data
  end

  var cover_url = metron_get_cover_url(issue_detail)
  if cover_url == nil
    raise "value_error", "Metron issue has no cover image URL"
  end

  # Cover images are normally hosted separately and do not need API credentials.
  if path.exists(output_path)
    path.remove(output_path)
  end
  var image_client = webclient()
  image_client.begin(cover_url)
  var status = image_client.GET()
  if status != 200
    image_client.close()
    raise "network_error", "Cover download returned HTTP " + str(status)
  end
  var written = image_client.write_file(output_path)
  image_client.close()
  if written <= 0
    if path.exists(output_path)
      path.remove(output_path)
    end
    raise "network_error", "Could not save the Metron cover image"
  end
  return written
end

def install_downloaded_cover()
  # Keep the last successfully displayed source if the download or rename fails.
  if path.exists(comic_backup_path) && !path.exists(comic_source_path)
    path.rename(comic_backup_path, comic_source_path)
  end
  if path.exists(comic_backup_path)
    path.remove(comic_backup_path)
  end
  var has_previous = path.exists(comic_source_path)
  if has_previous && !path.rename(comic_source_path, comic_backup_path)
    raise "io_error", "Could not back up the previous comic image"
  end
  if !path.rename(comic_download_path, comic_source_path)
    if has_previous
      path.rename(comic_backup_path, comic_source_path)
    end
    raise "io_error", "Could not install the downloaded comic image"
  end
end

def display_comic(username, password, series_name)
  if series_name == nil || size(series_name) == 0
    series_name = "batman"
  end
  if username == nil || password == nil || size(username) == 0 || size(password) == 0
    raise "value_error", "Pass your Metron username and password"
  end

  print("Fetching a random Metron comic cover...")
  var downloaded_bytes = metron_download_cover(username, password,
                                                series_name, comic_download_path)
  install_downloaded_cover()
  print("Downloaded " + str(downloaded_bytes) + " bytes")

  # inky_dither normalizes the source to 800x480, dithers it, then refreshes Inky.
  import inky_dither
  var result = nil
  try
    result = inky_dither(comic_source_path, comic_dithered_path, 0.5, 85)
  except .. as err, msg
    if path.exists(comic_source_path)
      path.remove(comic_source_path)
    end
    if path.exists(comic_backup_path)
      path.rename(comic_backup_path, comic_source_path)
    end
    raise err, msg
  end
  if path.exists(comic_backup_path)
    path.remove(comic_backup_path)
  end
  print("Displayed Metron cover: " + result["path"])
  return result
end

def start(username, password, series_name)
  print("Starting Metron comic display")
  var result = display_comic(username, password, series_name)
  print("Comic display started. Schedule display_comic(username, password, series) with a Tasmota rule for updates.")
  return {"status": "started", "image": result["path"]}
end
