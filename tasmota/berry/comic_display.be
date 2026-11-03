# Fetches a comic cover from Metron and displays it on Inky Impression.
#
# Usage:
#   load("comic_display.be")
#   start("METRON_USERNAME", "METRON_PASSWORD", "Batman")
#
# Pass nil or an empty string to choose a random series.
#
#   start("METRON_USERNAME", "METRON_PASSWORD", nil)

import path
import json

var metron_api = "https://metron.cloud/api/issue/"
var metron_series_api = "https://metron.cloud/api/series/"
var metron_user_agent = "TasmotaComicDisplay/1.0"
var metron_http_timeout_ms = 15000
var metron_connect_timeout_ms = 10000
var metron_retries = 3
var comic_source_path = "/metron_comic.jpg"
var comic_download_path = "/metron_comic.download"
var comic_backup_path = "/metron_comic.backup"
var comic_dithered_path = "/metron_comic_dithered.jpg"
var comic_max_source_bytes = 512 * 1024
var comic_cover_attempts = 5

def metron_new_client(username, password)
  var wc = webclient()
  # Berry webclient defaults to a 2 s connect timeout, which is too short for
  # metron.cloud HTTPS/TLS and surfaces as HTP: Connection error -2.
  wc.set_useragent(metron_user_agent)
  wc.set_timeouts(metron_http_timeout_ms, metron_connect_timeout_ms)
  if username != nil && size(username) > 0
    wc.set_auth(username, password)
  end
  return wc
end

def metron_should_retry(status)
  return status < 100 || status == 408 || status == 429 || status >= 500
end

def metron_status_message(status, server_header, content_type, location_header)
  # Async webclient maps a failed TCP/TLS connect to -2 (send header failed).
  if status == -1 || status == -2
    return "Cannot reach metron.cloud (webclient " + str(status) +
           "). TCP/TLS never completed; Metron often firewalls home IPs. Open https://metron.cloud/ from a browser on the same network, or call diagnose_network()."
  end
  if status < 100 || status > 599
    return "Metron request did not receive a valid HTTP status (webclient result=" + str(status) +
           ", server=" + server_header + ", content-type=" + content_type +
           ", location=" + location_header + ")"
  end
  return "Metron API returned HTTP " + str(status) +
         " (server=" + server_header + ", content-type=" + content_type +
         ", location=" + location_header + ")"
end

def diagnose_network()
  print("WiFi: " + str(tasmota.wifi()))
  var targets = ["https://example.com/", "https://metron.cloud/"]
  var names = ["example.com", "metron.cloud"]
  var i = 0
  while i < size(targets)
    var wc = metron_new_client(nil, nil)
    wc.begin(targets[i])
    var status = wc.GET()
    wc.close()
    print(names[i] + " -> " + str(status))
    i += 1
  end
end

def metron_get_json(url, username, password)
  var wc = nil
  var status = 0
  var attempt = 0
  while attempt < metron_retries
    attempt += 1
    wc = metron_new_client(username, password)
    wc.collect_headers("Server", "Content-Type", "Location", "Transfer-Encoding", "Connection")
    wc.begin(url)
    status = wc.GET()
    if status == 200
      break
    end
    var server_header = wc.get_header("Server")
    var content_type = wc.get_header("Content-Type")
    var location_header = wc.get_header("Location")
    wc.close()
    wc = nil
    if !metron_should_retry(status) || attempt >= metron_retries
      raise "network_error", metron_status_message(status, server_header, content_type, location_header)
    end
    print("Metron request failed with " + str(status) + ", retrying (" + str(attempt) + "/" + str(metron_retries) + ")")
    tasmota.delay(500)
  end

  var response_size = wc.get_size()
  print("Metron API response size: " + str(response_size) + " bytes")
  if response_size >= 32767
    wc.close()
    raise "value_error", "Metron API response exceeds Berry's 32 KB limit; check the API filters"
  end
  var response = wc.get_string()
  var transfer_encoding = wc.get_header("Transfer-Encoding")
  var connection_header = wc.get_header("Connection")
  var server_header = wc.get_header("Server")
  var content_type = wc.get_header("Content-Type")
  wc.close()
  if response == nil || size(response) == 0
    raise "network_error", "Metron API returned an empty response (HTTP " + str(status) +
          ", size=" + str(response_size) + ", transfer-encoding=" + transfer_encoding +
          ", connection=" + connection_header + ", server=" + server_header +
          ", content-type=" + content_type + ")"
  end

  var data = json.load(response)
  if data == nil
    raise "value_error", "Could not parse Metron API response"
  end
  return data
end

def metron_get_cover_url(issue_detail)
  if !isinstance(issue_detail, map)
    return nil
  end
  # Mokkari exposes this field as a string. Accept common nested API shapes too.
  for field : ["image", "cover", "cover_image", "cover_url", "image_url"]
    var value = issue_detail.find(field)
    if value != nil
      if type(value) == "string" && size(value) > 0
        return value
      end
      if isinstance(value, map)
        for nested_field : ["original_url", "image_url", "url"]
          var nested_value = value.find(nested_field)
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
  var seed = int(tasmota.millis()) & 0x7FFFFFFF
  var series_data = nil
  var series_url = nil
  if series_name == nil || size(series_name) == 0
    var first_page = metron_get_json(metron_series_api + "?page_size=1", username, password)
    var first_page_results = first_page.find("results")
    var series_count = first_page.find("count", 0)
    if first_page_results == nil || size(first_page_results) == 0 || series_count == nil || series_count < 1
      raise "value_error", "No Metron series found"
    end
    var page_size = size(first_page_results)
    var page_count = int((series_count + page_size - 1) / page_size)
    var series_page = (seed % page_count) + 1
    print("Searching a random Metron series (page " + str(series_page) + " of " + str(page_count) + ")")
    if series_page == 1
      series_data = first_page
    else
      series_url = metron_series_api + "?page=" + str(series_page) + "&page_size=1"
      series_data = metron_get_json(series_url, username, password)
    end
  else
    print("Searching Metron series: " + series_name)
    var encoded_series = webclient.url_encode(series_name)
    # Quick search also matches a series' alternative names.
    series_url = metron_series_api + "?q=" + encoded_series + "&page_size=1"
#     print("Metron series query: " + series_url)
    series_data = metron_get_json(series_url, username, password)
  end
  var series_results = series_data.find("results")
  if series_results == nil || size(series_results) == 0
    if series_name == nil || size(series_name) == 0
      raise "value_error", "No Metron series found"
    end
    raise "value_error", "No Metron series found for: " + series_name
  end

  # Metron series endpoint returns the title under 'series' (or fallback 'name')
  var series = series_results[seed % size(series_results)]
  var series_id = series.find("id")
  if series_id == nil
    raise "value_error", "Metron series result has no ID"
  end
  var series_title = series.find("series")
  if series_title == nil
    series_title = series.find("name", str(series_id))
  end
  print("Searching issues in " + str(series_title) + " (series " + str(series_id) + ")")

  var total_issues = series.find("issue_count", 0)
  if total_issues == nil || total_issues < 1
    total_issues = 20
  end

  # The issue-list filter takes 'series_id', not 'series'. Query specific issue numbers
  # and keep the response small.
  var issue = nil
  for attempt : range(0, 3)
    var candidate_number = ((seed % total_issues + attempt * 37) % total_issues) + 1
    var issue_url = metron_api + "?series_id=" + str(series_id) + "&number=" + str(candidate_number) + "&page_size=1"
    var issue_data = metron_get_json(issue_url, username, password)
    var issue_results = issue_data.find("results")
    if issue_results != nil && size(issue_results) > 0
      issue = issue_results[seed % size(issue_results)]
      break
    end
  end

  if issue == nil
    raise "value_error", "No Metron issues found in series: " + str(series_title)
  end
  if issue.find("id") == nil
    raise "value_error", "Metron issue result has no ID"
  end

  var issue_name = issue.find("issue")
  if issue_name == nil
    issue_name = issue.find("issue_name", issue.find("name"))
  end
  if issue_name != nil
    print("Fetching cover for: " + str(issue_name))
  end

  # Check if issue summary already contains the cover URL (avoids extra 21KB API call)
  var cover_url = metron_get_cover_url(issue)
  if cover_url == nil
    var issue_detail_url = metron_api + str(issue.find("id")) + "/"
    var issue_detail_data = metron_get_json(issue_detail_url, username, password)
    var issue_detail = issue_detail_data.find("results", issue_detail_data)
    cover_url = metron_get_cover_url(issue_detail)
  end

  if cover_url == nil
    raise "value_error", "Metron issue has no cover image URL"
  end

  # Cover images are normally hosted separately and do not need API credentials.
  if path.exists(output_path)
    path.remove(output_path)
  end
  var image_client = nil
  var status = 0
  var attempt = 0
  while attempt < metron_retries
    attempt += 1
    image_client = metron_new_client(nil, nil)
    image_client.begin(cover_url)
    status = image_client.GET()
    if status == 200
      break
    end
    image_client.close()
    image_client = nil
    if !metron_should_retry(status) || attempt >= metron_retries
      raise "network_error", "Cover download returned HTTP " + str(status)
    end
    print("Cover download failed with " + str(status) + ", retrying (" + str(attempt) + "/" + str(metron_retries) + ")")
    tasmota.delay(500)
  end
  var response_size = image_client.get_size()
  if response_size > comic_max_source_bytes
    image_client.close()
    return response_size
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
  if username == nil || password == nil || size(username) == 0 || size(password) == 0
    raise "value_error", "Pass your Metron username and password"
  end

  var downloaded_bytes = 0
  var cover_attempt = 0
  while cover_attempt < comic_cover_attempts
    cover_attempt += 1
    print("Fetching a random Metron comic cover (attempt " + str(cover_attempt) + "/" + str(comic_cover_attempts) + ")...")
    downloaded_bytes = metron_download_cover(username, password,
                                              series_name, comic_download_path)
    if downloaded_bytes <= comic_max_source_bytes
      break
    end
    print("Metron cover is " + str(downloaded_bytes) + " bytes; exceeds the 512 KiB limit, searching for another cover")
    if path.exists(comic_download_path)
      path.remove(comic_download_path)
    end
  end
  if downloaded_bytes > comic_max_source_bytes
    print("No Metron cover within 512 KiB found after " + str(comic_cover_attempts) + " attempts; keeping the current image")
    return nil
  end

  install_downloaded_cover()
  print("Downloaded " + str(downloaded_bytes) + " bytes")

  # inky_dither normalizes the source to the logical display dimensions, dithers it, then refreshes Inky.
  var dither_fn = nil
  import global
  if global.inky_dither != nil
    dither_fn = global.inky_dither
  else
    try
      import inky_dither
      if inky_dither != nil
        dither_fn = inky_dither
      end
    except .. as err, msg
      print("Could not import inky_dither: " + str(err) + " - " + str(msg))
    end
    if dither_fn == nil
      try
        tasmota.load("inky_dither.be")
        if global.inky_dither != nil
          dither_fn = global.inky_dither
        end
      except .. as err, msg
        print("Could not load inky_dither.be: " + str(err) + " - " + str(msg))
      end
    end
  end

  if dither_fn == nil
    raise "value_error", "inky_dither function is not loaded. Upload or run load('inky_dither.be') first."
  end

  var result = nil
  try
    result = dither_fn(comic_source_path, comic_dithered_path, 0.5, 85)
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
  var image_path = result != nil ? result.find("path", comic_dithered_path) : comic_dithered_path
  print("Displayed Metron cover: " + str(image_path))
  return result
end

def start(username, password, series_name)
  print("Starting Metron comic display")
  var result = display_comic(username, password, series_name)
  if result == nil
    return {"status": "no_suitable_cover"}
  end
  print("Comic display started. Schedule display_comic(username, password, series) with a Tasmota rule for updates.")
  var image_path = result != nil ? result.find("path", comic_dithered_path) : comic_dithered_path
  return {"status": "started", "image": image_path}
end
