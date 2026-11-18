# Fetches a comic cover from Metron and displays it on Inky Impression.
#
# Usage:
#   load("comic_display.be")
#   display_comic_from_config()
#
# The scheduled wrapper reads credentials from /metron_comic_account.json.
# Pass nil or an empty string to choose a random series when using start().
#
#   start("METRON_USERNAME", "METRON_PASSWORD", "Batman")
#
# For correct Inky output orientation, set the Tasmota command DisplayRotate 1
# (90 degrees) before running this script.
#
# SECURITY NOTE: async webclient builds pin the Metron API public key before
# sending credentials. Other builds keep the legacy webclient behavior, which
# accepts any TLS certificate; use those builds only on trusted networks.
#
# Credentials are only sent to https://metron.cloud API endpoints. The cover
# image download never sends credentials, and HTTP redirects are not followed,
# so the Authorization header cannot leak to another host.

import path
import json
import gc
import math

var metron_api = "https://metron.cloud/api/issue/"
var metron_series_api = "https://metron.cloud/api/series/"
var metron_user_agent = "TasmotaComicDisplay/1.0"
var metron_http_timeout_ms = 15000
var metron_connect_timeout_ms = 10000
var metron_retries = 3
# BearSSL SHA-1 public-key pin for metron.cloud, captured after hostname and
# certificate-chain validation on 2026-11-17. A key rotation requires updating it.
var metron_tls_pubkey_pin = "057743768c452c97d36a7b8cda80a5a551f664cf"
var metron_async_available = false
var metron_security_warning_printed = false
var comic_source_path = "/metron_comic.jpg"
var comic_download_path = "/metron_comic.download"
var comic_backup_path = "/metron_comic.backup"
var comic_dithered_path = "/metron_comic_dithered.jpg"
var comic_api_response_path = "/metron_api_response.json"
var comic_account_path = "/metron_comic_account.json"
var comic_max_source_bytes = 1024 * 1024
var comic_max_api_bytes = 128 * 1024
var comic_cover_attempts = 5
var metron_body_limit_error = -13
var metron_async_display

def metron_new_client(username, password, pin_metron, async_body_limit)
  var wc = webclient()
  var async_client = false
  try
    # This call both detects async TLS support and pins the API connection.
    # Pin before setting credentials or beginning the request.
    wc.tls_pin_pubkey(metron_tls_pubkey_pin)
    async_client = true
    if !pin_metron
      # Cover hosts are independent and receive no credentials.
      wc.tls_clear_pins()
    end
  except .. as err, msg
    if err != "attribute_error" && msg != "wc_tls_pin_pubkey command unavailable in non-async webclient build."
      raise err, msg
    end
  end
  if async_client
    wc.async_set_body_limit(async_body_limit)
  end
  metron_async_available = async_client
  if !async_client && username != nil && size(username) > 0 && !metron_security_warning_printed
    print("WARNING: this firmware lacks async TLS pinning; webclient() accepts any TLS certificate")
    metron_security_warning_printed = true
  end
  # Berry webclient defaults to a 2 s connect timeout, which is too short for
  # metron.cloud HTTPS/TLS and surfaces as HTP: Connection error -2.
  wc.set_useragent(metron_user_agent)
  wc.set_timeouts(metron_http_timeout_ms, metron_connect_timeout_ms)
  # Keep redirects disabled (the default) so credentials are never forwarded
  # to a different host if metron.cloud ever answers with a redirect.
  wc.set_follow_redirects(false)
  if username != nil && size(username) > 0
    wc.set_auth(username, password)
  end
  return wc
end

def metron_http_status(wc, state)
  var status = wc.last_code
  if status >= 200 && status < 300
    var received = wc.last_rx
    if received == metron_body_limit_error
      return metron_body_limit_error
    end
    if state != 2 || received < 0
      return received < 0 ? received : -11
    end
  end
  return status
end

def metron_http_poll(wc, on_complete)
  var state = wc.async_state()
  if state == 1
    tasmota.set_timer(50, def () metron_http_poll(wc, on_complete) end)
    return
  end
  on_complete(metron_http_status(wc, state))
end

def metron_http_get(wc, on_complete)
  if !metron_async_available
    return wc.GET()
  end
  var rc = wc.async_get_start()
  if rc != 1
    return rc
  end
  tasmota.set_timer(50, def () metron_http_poll(wc, on_complete) end)
  return nil
end

def metron_should_retry(status)
  if status == metron_body_limit_error
    return false
  end
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
    var body_limit = targets[i] == "https://metron.cloud/" ? comic_max_api_bytes : 16384
    var wc = metron_new_client(nil, nil, targets[i] == "https://metron.cloud/", body_limit)
    wc.begin(targets[i])
    var status = wc.GET()
    tasmota.yield()
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
    wc = metron_new_client(username, password, true, comic_max_api_bytes)
    wc.collect_headers("Server", "Content-Type", "Location", "Transfer-Encoding", "Connection")
    wc.begin(url)
    status = wc.GET()
    tasmota.yield()
    if status >= 200 && status < 300
      break
    end
    if status == metron_body_limit_error
      wc.close()
      raise "value_error", "Metron API response exceeds the configured body limit"
    end
    var server_header = wc.get_header("Server")
    var content_type = wc.get_header("Content-Type")
    var location_header = wc.get_header("Location")
    wc.close()
    wc = nil
    var status_message = metron_status_message(status, server_header, content_type, location_header)
    if !metron_should_retry(status)
      raise "http_error", status_message
    end
    if attempt >= metron_retries
      raise "network_error", status_message
    end
    print("Metron request failed with " + str(status) + ", retrying (" + str(attempt) + "/" + str(metron_retries) + ")")
    tasmota.delay(500)
  end

  var response_size = wc.get_size()
  print("Metron API response size: " + str(response_size) + " bytes")
  # get_size() is negative when the response has no Content-Length, including
  # chunked responses. Reject these before reading because the legacy webclient
  # has no bounded-response API.
  if response_size < 0
    wc.close()
    raise "network_error", "Metron API response has no Content-Length; refusing an unbounded download"
  end
  if response_size > comic_max_api_bytes
    wc.close()
    raise "value_error", "Metron API response exceeds 128 KB; check the API filters"
  end
  var response = nil
  if response_size >= 32767
    # wc.get_string() refuses bodies >= 32 KB, but Berry strings allow far more.
    # Stream the body to a file and read it back instead.
    var saved = wc.write_file(comic_api_response_path)
    tasmota.yield()
    if saved <= 0
      wc.close()
      if path.exists(comic_api_response_path)
        path.remove(comic_api_response_path)
      end
      raise "network_error", "Could not save the Metron API response"
    end
    var response_file = open(comic_api_response_path, "rb")
    response = response_file.read()
    response_file.close()
    path.remove(comic_api_response_path)
  else
    response = wc.get_string()
  end
  tasmota.yield()
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
  if size(response) != response_size
    raise "network_error", "Metron API response was truncated (expected " + str(response_size) +
          " bytes, received " + str(size(response)) + ")"
  end

  var data = json.load(response)
  response = nil
  gc.collect()
  if data == nil
    raise "value_error", "Could not parse Metron API response"
  end
  tasmota.yield()
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

def metron_download_cover(username, password, series_name, output_path, on_complete)
  var seed = int(tasmota.millis()) & 0x7FFFFFFF
  var series_data = nil
  var series_url = nil
  var random_series = series_name == nil || size(series_name) == 0
  var series_offset = 0
  var series_page = 1
  var first_page = nil
  var first_page_results = nil
  if random_series
    first_page = metron_get_json(metron_series_api + "?page_size=20", username, password)
    first_page_results = first_page.find("results")
    var series_count = first_page.find("count", 0)
    if first_page_results == nil || size(first_page_results) == 0 || series_count == nil || series_count < 1
      raise "value_error", "No Metron series found"
    end
    var page_size = size(first_page_results)
    var page_count = int((series_count + page_size - 1) / page_size)
    var series_index = seed % series_count
    series_page = int(series_index / page_size) + 1
    series_offset = series_index % page_size
    print("Searching a random Metron series (page " + str(series_page) + " of " + str(page_count) + ")")
    if series_page == 1
      series_data = first_page
    else
      series_url = metron_series_api + "?page=" + str(series_page) + "&page_size=" + str(page_size)
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
  if series_results == nil
    raise "value_error", "Metron series response has no results"
  end
  if size(series_results) == 0
    if random_series && series_page > 1
      raise "selection_error", "Metron series page changed during selection"
    end
    if series_name == nil || size(series_name) == 0
      raise "value_error", "No Metron series found"
    end
    raise "value_error", "No Metron series found for: " + series_name
  end

  # Metron series endpoint returns the title under 'series' (or fallback 'name')
  var series = nil
  if random_series
    if series_offset >= size(series_results)
      raise "selection_error", "Metron series page changed during selection"
    end
    series = series_results[series_offset]
  else
    series = series_results[seed % size(series_results)]
  end
  var series_id = series.find("id")
  if series_id == nil
    raise "value_error", "Metron series result has no ID"
  end
  var series_title = series.find("series")
  if series_title == nil
    series_title = series.find("name", str(series_id))
  end
  print("Searching issues in " + str(series_title) + " (series " + str(series_id) + ")")
  series = nil
  series_results = nil
  series_data = nil
  first_page = nil
  first_page_results = nil
  gc.collect()

  # The issue-list filter takes 'series_id', not 'series'. Use pagination because
  # issue_count is a count, not a range of valid issue numbers.
  var issue_url = metron_api + "?series_id=" + str(series_id) + "&page_size=20"
  var first_issue_page = metron_get_json(issue_url, username, password)
  var issue_count = first_issue_page.find("count", 0)
  var first_issue_results = first_issue_page.find("results", [])
  var issue_page_size = size(first_issue_results)
  if issue_count == nil || issue_count < 1 || issue_page_size < 1
    raise "value_error", "No Metron issues found in series: " + str(series_title)
  end
  var issue_index = math.rand() % issue_count
  var issue_page = int(issue_index / issue_page_size) + 1
  var issue_offset = issue_index % issue_page_size
  var issue_data = first_issue_page
  if issue_page > 1
    issue_url = metron_api + "?series_id=" + str(series_id) + "&page=" + str(issue_page) + "&page_size=" + str(issue_page_size)
    issue_data = metron_get_json(issue_url, username, password)
  end
  var issue_results = issue_data.find("results")
  if issue_results == nil
    raise "value_error", "Metron issue page has no results"
  end
  if size(issue_results) == 0
    if issue_page > 1
      raise "selection_error", "Metron issue page changed during selection"
    end
    raise "value_error", "No Metron issues found in series: " + str(series_title)
  end
  var issue = nil
  if issue_offset < size(issue_results)
    issue = issue_results[issue_offset]
  else
    raise "selection_error", "Metron issue page changed during selection"
  end

  if issue == nil
    raise "value_error", "Metron issue response is invalid"
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
  var issue_id = issue.find("id")
  var issue_detail_data = nil
  var issue_detail = nil
  if cover_url == nil
    var issue_detail_url = metron_api + str(issue_id) + "/"
    issue_detail_data = metron_get_json(issue_detail_url, username, password)
    issue_detail = issue_detail_data.find("results", issue_detail_data)
    cover_url = metron_get_cover_url(issue_detail)
  end

  if cover_url == nil
    raise "cover_unavailable", "Metron issue has no cover image URL"
  end
  first_issue_page = nil
  first_issue_results = nil
  issue_data = nil
  issue_results = nil
  issue = nil
  issue_name = nil
  issue_detail = nil
  issue_detail_data = nil
  gc.collect()

  # Cover images are normally hosted separately and do not need API credentials.
  if path.exists(output_path)
    path.remove(output_path)
  end
  var image_client = nil
  var status = 0
  var attempt = 0
  while attempt < metron_retries
    attempt += 1
    image_client = metron_new_client(nil, nil, false, comic_max_source_bytes)
    image_client.begin(cover_url)
    if on_complete != nil
      status = metron_http_get(image_client, def (completed_status)
        on_complete(image_client, completed_status)
      end)
      if status == nil
        return "pending"
      end
    else
      status = image_client.GET()
    end
    tasmota.yield()
    if status >= 200 && status < 300
      break
    end
    if status == metron_body_limit_error
      image_client.close()
      raise "body_too_large", "Cover response exceeds the configured body limit"
    end
    image_client.close()
    image_client = nil
    if !metron_should_retry(status)
      raise "cover_unavailable", "Cover download returned HTTP " + str(status)
    end
    if attempt >= metron_retries
      raise "network_error", "Cover download returned HTTP " + str(status)
    end
    print("Cover download failed with " + str(status) + ", retrying (" + str(attempt) + "/" + str(metron_retries) + ")")
    tasmota.delay(500)
  end
  var response_size = image_client.get_size()
  # write_file() cannot cap an unknown-length response while streaming it.
  if response_size < 0
    image_client.close()
    raise "network_error", "Cover response has no Content-Length; refusing an unbounded download"
  end
  if response_size > comic_max_source_bytes
    image_client.close()
    return response_size
  end
  var written = image_client.write_file(output_path)
  tasmota.yield()
  image_client.close()
  if written != response_size
    if path.exists(output_path)
      path.remove(output_path)
    end
    raise "network_error", "Metron cover was truncated or could not be saved"
  end
  return written
end

def install_downloaded_cover()
  # Keep the last successfully displayed source if the download or rename fails.
  if path.exists(comic_backup_path) && !path.exists(comic_source_path)
    if !path.rename(comic_backup_path, comic_source_path)
      raise "io_error", "Could not restore the previous comic image"
    end
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
      if !path.rename(comic_backup_path, comic_source_path)
        raise "io_error", "Could not restore the previous comic image"
      end
    end
    raise "io_error", "Could not install the downloaded comic image"
  end
end

def metron_async_retry(username, password, series_name, dither_fn, attempt, reason)
  if attempt < comic_cover_attempts
    print(reason + "; searching for another cover")
    gc.collect()
    tasmota.set_timer(500, def ()
      metron_async_display(username, password, series_name, dither_fn, attempt + 1)
    end)
  else
    print("No Metron cover could be processed after " + str(comic_cover_attempts) + " attempts; keeping the current image")
  end
end

def metron_async_cover_complete(username, password, series_name, dither_fn, attempt, image_client, status)
  if status < 200 || status >= 300
    image_client.close()
    if path.exists(comic_download_path)
      path.remove(comic_download_path)
    end
    metron_async_retry(username, password, series_name, dither_fn, attempt,
                       "Metron cover request failed with HTTP " + str(status))
    return
  end

  var response_size = image_client.last_rx
  if response_size < 0 || response_size > comic_max_source_bytes
    image_client.close()
    if path.exists(comic_download_path)
      path.remove(comic_download_path)
    end
    metron_async_retry(username, password, series_name, dither_fn, attempt,
                       "Metron cover response has an invalid size: " + str(response_size))
    return
  end

  var written = image_client.write_file(comic_download_path)
  image_client.close()
  if written != response_size
    if path.exists(comic_download_path)
      path.remove(comic_download_path)
    end
    metron_async_retry(username, password, series_name, dither_fn, attempt,
                       "Metron cover was truncated or could not be saved")
    return
  end

  try
    install_downloaded_cover()
    var result = dither_fn(comic_source_path, comic_dithered_path, 0.5, 85, nil, nil, nil, 0.75)
    tasmota.yield()
    if result == nil
      raise "img_error", "dithering failed"
    end
    if path.exists(comic_backup_path)
      path.remove(comic_backup_path)
    end
    var image_path = result.find("path", comic_dithered_path)
    var refresh = result.find("refresh_status", "not_requested")
    if refresh == "complete"
      print("Displayed Metron cover from RGB buffer; JPEG saved: " + str(image_path))
    elif refresh == "running"
      print("Metron cover RGB buffer refresh started; JPEG saved: " + str(image_path))
    elif refresh == "failed"
      print("Metron cover JPEG saved, but RGB buffer display refresh failed: " + str(image_path))
    elif refresh == "not_started"
      print("Metron cover refresh was not started (display busy or unavailable); JPEG saved: " + str(image_path))
    else
      print("Dithered Metron cover JPEG saved without a display refresh: " + str(image_path))
    end
  except .. as err, msg
    if path.exists(comic_source_path)
      path.remove(comic_source_path)
    end
    if path.exists(comic_backup_path)
      if !path.rename(comic_backup_path, comic_source_path)
        raise "io_error", "Could not restore the previous comic image"
      end
    end
    if err == "img_error"
      metron_async_retry(username, password, series_name, dither_fn, attempt,
                         "Could not process this Metron cover (" + str(msg) + ")")
    else
      print("Could not display the Metron cover: " + str(err) + " - " + str(msg))
    end
  end
end

metron_async_display = def (username, password, series_name, dither_fn, attempt)
  if attempt > comic_cover_attempts
    return {"status": "no_suitable_cover"}
  end
  print("Fetching a random Metron comic cover (attempt " + str(attempt) + "/" + str(comic_cover_attempts) + ")...")
  try
    var downloaded = metron_download_cover(username, password, series_name, comic_download_path,
      def (image_client, status)
        metron_async_cover_complete(username, password, series_name, dither_fn,
                                    attempt, image_client, status)
      end)
    if downloaded == "pending"
      return {"status": "pending"}
    end
    return {"status": "pending"}
  except .. as err, msg
    if err == "selection_error" || err == "body_too_large" || err == "network_error" || err == "cover_unavailable"
      metron_async_retry(username, password, series_name, dither_fn, attempt,
                         "Metron request failed: " + str(msg))
      return {"status": "pending"}
    end
    print("Could not fetch a Metron cover: " + str(err) + " - " + str(msg))
    return {"status": "no_suitable_cover"}
  end
end

def display_comic(username, password, series_name)
  if username == nil || password == nil || size(username) == 0 || size(password) == 0
    raise "value_error", "Pass your Metron username and password"
  end
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

  # Detect async support before choosing the cover-download path on the first run.
  var capability_client = metron_new_client(username, password, true, comic_max_api_bytes)
  capability_client.close()
  if metron_async_available
    return metron_async_display(username, password, series_name, dither_fn, 1)
  end

  var downloaded_bytes = 0
  var result = nil
  var cover_was_under_limit = false
  var network_failed = false
  var cover_attempt = 0
  while cover_attempt < comic_cover_attempts
    cover_attempt += 1
    print("Fetching a random Metron comic cover (attempt " + str(cover_attempt) + "/" + str(comic_cover_attempts) + ")...")
    try
      downloaded_bytes = metron_download_cover(username, password,
                                                series_name, comic_download_path, nil)
    except .. as err, msg
      if err == "selection_error"
        print("Metron pagination changed during selection; retrying with a new selection")
        gc.collect()
        if cover_attempt < comic_cover_attempts
          continue
        end
        break
      end
      if err == "body_too_large"
        print("Metron cover exceeds the 1024 KiB limit; searching for another cover")
        gc.collect()
        if cover_attempt < comic_cover_attempts
          continue
        end
        break
      end
      if err == "network_error" || err == "cover_unavailable"
        network_failed = true
        print("Metron network request failed: " + str(msg) + "; searching for another cover")
        if path.exists(comic_download_path)
          path.remove(comic_download_path)
        end
        gc.collect()
        if cover_attempt < comic_cover_attempts
          continue
        end
        break
      end
      raise err, msg
    end
    tasmota.yield()
    if downloaded_bytes > comic_max_source_bytes
      print("Metron cover is " + str(downloaded_bytes) + " bytes; exceeds the 1024 KiB limit, searching for another cover")
      if path.exists(comic_download_path)
        path.remove(comic_download_path)
      end
      continue
    end

    cover_was_under_limit = true
    install_downloaded_cover()
    tasmota.yield()
    print("Downloaded " + str(downloaded_bytes) + " bytes")
    try
      result = dither_fn(comic_source_path, comic_dithered_path, 0.5, 85, nil, nil, nil, 0.75)
      tasmota.yield()
      break
    except .. as err, msg
      if path.exists(comic_source_path)
        path.remove(comic_source_path)
      end
      if path.exists(comic_backup_path)
        if !path.rename(comic_backup_path, comic_source_path)
          raise "io_error", "Could not restore the previous comic image"
        end
      end
      if err == "img_error" && (msg == "no compatible jpg buffer" || msg == "jpg decoding failed" || msg == "could not decode or resize JPEG" || msg == "image exceeds available PSRAM" || msg == "reallocation failed")
        gc.collect()
        print("Could not decode this Metron cover (" + str(msg) + "); searching for another cover")
        if cover_attempt < comic_cover_attempts
          continue
        end
        break
      end
      if err == "img_error" && msg == "not enough memory to resize image"
        gc.collect()
        print("Not enough memory to resize this Metron cover; searching for another cover")
        if cover_attempt < comic_cover_attempts
          continue
        end
        break
      end
      raise err, msg
    end
  end
  if result == nil
    if cover_was_under_limit
      print("No Metron cover could be processed after " + str(comic_cover_attempts) + " attempts; keeping the current image")
    elif network_failed
      print("No usable Metron cover after " + str(comic_cover_attempts) + " attempts (network errors occurred); keeping the current image")
    else
      print("No Metron cover within 1024 KiB found after " + str(comic_cover_attempts) + " attempts; keeping the current image")
    end
    return nil
  end
  if path.exists(comic_backup_path)
    path.remove(comic_backup_path)
  end
  var image_path = result != nil ? result.find("path", comic_dithered_path) : comic_dithered_path
  var refresh = result.find("refresh_status", "not_requested")
  if refresh == "complete"
    print("Displayed Metron cover from RGB buffer; JPEG saved: " + str(image_path))
  elif refresh == "running"
    print("Metron cover RGB buffer refresh started; JPEG saved: " + str(image_path))
  elif refresh == "failed"
    print("Metron cover JPEG saved, but RGB buffer display refresh failed: " + str(image_path))
  elif refresh == "not_started"
    print("Metron cover refresh was not started (display busy or unavailable); JPEG saved: " + str(image_path))
  else
    print("Dithered Metron cover JPEG saved without a display refresh: " + str(image_path))
  end
  return result
end

def display_comic_from_config()
  var account_file = nil
  var account = nil
  try
    account_file = open(comic_account_path, "r")
    account = json.load(account_file.read())
    account_file.close()
    account_file = nil
  except .. as err, msg
    if account_file != nil
      account_file.close()
    end
    raise "value_error", "Could not read Metron account configuration at " + comic_account_path
  end

  if !isinstance(account, map)
    raise "value_error", "Metron account configuration must be a JSON object"
  end
  var username = account.find("username")
  var password = account.find("password")
  if type(username) != "string" || size(username) == 0 ||
     type(password) != "string" || size(password) == 0
    raise "value_error", "Metron account configuration needs non-empty username and password strings"
  end
  return display_comic(username, password, nil)
end

def start(username, password, series_name)
  print("Starting Metron comic display")
  var result = display_comic(username, password, series_name)
  if result == nil
    return {"status": "no_suitable_cover"}
  end
  if result.find("status") == "pending"
    return result
  end
  var image_path = result != nil ? result.find("path", comic_dithered_path) : comic_dithered_path
  var refresh = result.find("refresh_status", "not_requested")
  var displayed = refresh == "complete"
  var status = "saved"
  if refresh == "complete"
    status = "displayed"
    print("Comic displayed. Schedule display_comic_from_config() with a Tasmota rule for updates.")
  elif refresh == "running"
    status = "started"
    print("Comic display refresh started. Schedule display_comic_from_config() with a Tasmota rule for updates.")
  elif refresh == "failed"
    status = "refresh_failed"
    print("Comic cover was saved, but the display refresh failed.")
  elif refresh == "not_started"
    status = "refresh_not_started"
    print("Comic cover saved; display refresh was not started because the display is busy or unavailable.")
  else
    print("Comic cover dithered and saved; no display is initialized.")
  end
  return {"status": status, "image": image_path,
          "displayed": displayed}
end
