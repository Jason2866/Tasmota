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
# SECURITY NOTE: this script requires the async webclient with TLS public-key
# pinning support. It pins the Metron API key before sending credentials.
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
var metron_async_api_request
var metron_async_fetch_series
var metron_async_choose_series
var metron_async_fetch_issues
var metron_async_choose_issue
var metron_async_start_cover
var metron_async_cover_complete

def metron_new_client(username, password, pin_metron, async_body_limit)
  var wc = webclient()
  try
    # Pin before setting credentials or beginning any request. Cover hosts are
    # independent and receive no credentials, so their pins are cleared below.
    wc.tls_pin_pubkey(metron_tls_pubkey_pin)
  except .. as err, msg
    if msg == "wc_tls_pin_pubkey command unavailable in non-async webclient build."
      raise "value_error", "This firmware requires the async webclient with TLS public-key pinning support"
    end
    raise err, msg
  end
  if !pin_metron
    # Cover hosts are independent and receive no credentials.
    wc.tls_clear_pins()
  end
  wc.async_set_body_limit(async_body_limit)
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

def metron_close_client(wc)
  if wc != nil
    wc.close()
    wc.deinit()
  end
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

def metron_http_poll(wc, on_complete, poll_count)
  var state = wc.async_state()
  if state == 1
    # Release temporary callback objects during long cover downloads.
    if poll_count % 10 == 0
      gc.collect()
    end
    tasmota.set_timer(50, def () metron_http_poll(wc, on_complete, poll_count + 1) end)
    return
  end
  on_complete(metron_http_status(wc, state))
end

def metron_http_get(wc, on_complete)
  var rc = wc.async_get_start()
  if rc != 1
    return rc
  end
  tasmota.set_timer(50, def () metron_http_poll(wc, on_complete, 1) end)
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
    return "Connection to metron.cloud did not complete (webclient " + str(status) +
           "). Check network connectivity and the configured TLS public-key pin; a rotated Metron key can cause this result. Run diagnose_network() for async connectivity checks."
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

def metron_async_api_result(url, username, password, on_complete, attempt, wc, status)
  var data = nil
  var response = nil
  var error_kind = nil
  var message = nil
  var retryable = metron_should_retry(status)
  try
    if status >= 200 && status < 300
      response = wc.get_string()
      if response == nil || size(response) == 0
        error_kind = "network_error"
        message = "Metron API returned an empty response"
        retryable = true
      elif wc.last_rx != size(response)
        error_kind = "network_error"
        message = "Metron API response was truncated (expected " + str(wc.last_rx) +
                  " bytes, received " + str(size(response)) + ")"
        retryable = true
      else
        data = json.load(response)
        if data == nil || !isinstance(data, map)
          error_kind = "value_error"
          message = "Metron API response is not a JSON object"
        end
      end
    else
      var server_header = wc.get_header("Server")
      var content_type = wc.get_header("Content-Type")
      var location_header = wc.get_header("Location")
      if server_header == nil server_header = "" end
      if content_type == nil content_type = "" end
      if location_header == nil location_header = "" end
      error_kind = status == metron_body_limit_error ? "body_too_large" :
                   retryable ? "network_error" : "http_error"
      message = metron_status_message(status, server_header, content_type, location_header)
    end
  except .. as err, msg
    error_kind = err
    message = msg
  end

  response = nil
  metron_close_client(wc)
  if error_kind != nil
    if retryable && attempt < metron_retries
      print("Metron API request failed with " + str(status) + ", retrying (" +
            str(attempt) + "/" + str(metron_retries) + ")")
      tasmota.set_timer(500, def ()
        metron_async_api_request(url, username, password, on_complete, attempt + 1)
      end)
      return
    end
    on_complete(nil, error_kind, message)
    return
  end

  gc.collect()
  on_complete(data, nil, nil)
end

metron_async_api_request = def (url, username, password, on_complete, attempt)
  var wc = nil
  var start_status = nil
  var error_kind = nil
  var message = nil
  try
    wc = metron_new_client(username, password, true, comic_max_api_bytes)
    wc.collect_headers("Server", "Content-Type", "Location")
    wc.begin(url)
    start_status = metron_http_get(wc, def (status)
      metron_async_api_result(url, username, password, on_complete, attempt, wc, status)
    end)
  except .. as err, msg
    error_kind = err
    message = msg
  end

  if error_kind != nil
    metron_close_client(wc)
    on_complete(nil, error_kind, message)
    return
  end
  if start_status != nil
    metron_async_api_result(url, username, password, on_complete, attempt, wc, start_status)
  end
end

def metron_async_diagnose_next(targets, names, index)
  if index >= size(targets)
    return
  end
  var target = targets[index]
  var wc = metron_new_client(nil, nil, target == "https://metron.cloud/",
                             target == "https://metron.cloud/" ? comic_max_api_bytes : 16384)
  wc.begin(target)
  var status = metron_http_get(wc, def (completed_status)
    metron_close_client(wc)
    print(names[index] + " -> " + str(completed_status))
    metron_async_diagnose_next(targets, names, index + 1)
  end)
  if status != nil
    metron_close_client(wc)
    print(names[index] + " -> " + str(status))
    metron_async_diagnose_next(targets, names, index + 1)
  end
end

def diagnose_network()
  print("WiFi: " + str(tasmota.wifi()))
  var targets = ["https://example.com/", "https://metron.cloud/"]
  var names = ["example.com", "metron.cloud"]
  print("Starting async network checks")
  metron_async_diagnose_next(targets, names, 0)
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

def metron_async_lookup_failed(ctx, error_kind, message)
  if error_kind == "selection_error" || error_kind == "body_too_large" ||
     error_kind == "network_error" || error_kind == "cover_unavailable"
    metron_async_retry(ctx.username, ctx.password, ctx.series_name, ctx.dither_fn,
                       ctx.attempt, message)
  else
    print("Could not fetch a Metron cover: " + str(error_kind) + " - " + str(message))
  end
end

def metron_async_fetch_series(ctx)
  var url = metron_series_api + "?page_size=20"
  if !ctx.random_series
    print("Searching Metron series: " + ctx.series_name)
    url = metron_series_api + "?q=" + webclient.url_encode(ctx.series_name) + "&page_size=1"
  end
  metron_async_api_request(url, ctx.username, ctx.password,
    def (data, error_kind, message)
      if error_kind != nil
        metron_async_lookup_failed(ctx, error_kind, message)
        return
      end
      var results = data.find("results")
      if results == nil || size(results) == 0
        metron_async_lookup_failed(ctx, "value_error", "No Metron series found")
        return
      end
      ctx.series_offset = 0
      if ctx.random_series
        var series_count = data.find("count", 0)
        var page_size = size(results)
        if series_count == nil || series_count < 1 || page_size < 1
          metron_async_lookup_failed(ctx, "value_error", "No Metron series found")
          return
        end
        var series_index = ctx.seed % series_count
        var series_page = int(series_index / page_size) + 1
        ctx.series_offset = series_index % page_size
        print("Searching a random Metron series (page " + str(series_page) + ")")
        if series_page > 1
          var page_url = metron_series_api + "?page=" + str(series_page) + "&page_size=" + str(page_size)
          metron_async_api_request(page_url, ctx.username, ctx.password,
            def (page_data, page_error, page_message)
              if page_error != nil
                metron_async_lookup_failed(ctx, page_error, page_message)
                return
              end
              metron_async_choose_series(ctx, page_data)
            end, 1)
          return
        end
      else
        ctx.series_offset = ctx.seed % size(results)
      end
      metron_async_choose_series(ctx, data)
    end, 1)
end

def metron_async_choose_series(ctx, data)
  var results = data.find("results")
  if results == nil || size(results) == 0 || ctx.series_offset >= size(results)
    metron_async_lookup_failed(ctx, "selection_error", "Metron series page changed during selection")
    return
  end
  var series = results[ctx.series_offset]
  var series_id = series.find("id")
  if series_id == nil
    metron_async_lookup_failed(ctx, "value_error", "Metron series result has no ID")
    return
  end
  ctx.series_id = series_id
  ctx.series_title = series.find("series", series.find("name", str(series_id)))
  print("Searching issues in " + str(ctx.series_title) + " (series " + str(series_id) + ")")
  data = nil
  gc.collect()
  metron_async_fetch_issues(ctx)
end

def metron_async_fetch_issues(ctx)
  var url = metron_api + "?series_id=" + str(ctx.series_id) + "&page_size=20"
  metron_async_api_request(url, ctx.username, ctx.password,
    def (data, error_kind, message)
      if error_kind != nil
        metron_async_lookup_failed(ctx, error_kind, message)
        return
      end
      var count = data.find("count", 0)
      var results = data.find("results", [])
      var page_size = size(results)
      if count == nil || count < 1 || page_size < 1
        metron_async_lookup_failed(ctx, "value_error", "No Metron issues found in series: " + str(ctx.series_title))
        return
      end
      var issue_index = math.rand() % count
      var issue_page = int(issue_index / page_size) + 1
      ctx.issue_offset = issue_index % page_size
      if issue_page > 1
        var page_url = metron_api + "?series_id=" + str(ctx.series_id) +
                       "&page=" + str(issue_page) + "&page_size=" + str(page_size)
        metron_async_api_request(page_url, ctx.username, ctx.password,
          def (page_data, page_error, page_message)
            if page_error != nil
              metron_async_lookup_failed(ctx, page_error, page_message)
              return
            end
            metron_async_choose_issue(ctx, page_data)
          end, 1)
        return
      end
      metron_async_choose_issue(ctx, data)
    end, 1)
end

def metron_async_choose_issue(ctx, data)
  var results = data.find("results")
  if results == nil || size(results) == 0 || ctx.issue_offset >= size(results)
    metron_async_lookup_failed(ctx, "selection_error", "Metron issue page changed during selection")
    return
  end
  var issue = results[ctx.issue_offset]
  if issue == nil || issue.find("id") == nil
    metron_async_lookup_failed(ctx, "value_error", "Metron issue response is invalid")
    return
  end
  var issue_name = issue.find("issue", issue.find("issue_name", issue.find("name")))
  if issue_name != nil
    print("Fetching cover for: " + str(issue_name))
  end
  var cover_url = metron_get_cover_url(issue)
  var issue_id = issue.find("id")
  data = nil
  issue = nil
  gc.collect()
  if cover_url != nil
    metron_async_start_cover(ctx, cover_url)
    return
  end
  metron_async_api_request(metron_api + str(issue_id) + "/", ctx.username, ctx.password,
    def (detail_data, error_kind, message)
      if error_kind != nil
        metron_async_lookup_failed(ctx, error_kind, message)
        return
      end
      var detail = detail_data.find("results", detail_data)
      cover_url = metron_get_cover_url(detail)
      detail_data = nil
      detail = nil
      gc.collect()
      if cover_url == nil
        metron_async_lookup_failed(ctx, "cover_unavailable", "Metron issue has no cover image URL")
        return
      end
      metron_async_start_cover(ctx, cover_url)
    end, 1)
end

def metron_async_start_cover(ctx, cover_url)
  if path.exists(comic_download_path)
    path.remove(comic_download_path)
  end
  var image_client = metron_new_client(nil, nil, false, comic_max_source_bytes)
  image_client.begin(cover_url)
  var status = metron_http_get(image_client, def (completed_status)
    metron_async_cover_complete(ctx.username, ctx.password, ctx.series_name, ctx.dither_fn,
                                ctx.attempt, image_client, completed_status)
  end)
  if status != nil
    metron_close_client(image_client)
    metron_async_retry(ctx.username, ctx.password, ctx.series_name, ctx.dither_fn,
                       ctx.attempt, "Metron cover request failed with HTTP " + str(status))
  end
end

def metron_async_cover_complete(username, password, series_name, dither_fn, attempt, image_client, status)
  if status < 200 || status >= 300
    metron_close_client(image_client)
    if path.exists(comic_download_path)
      path.remove(comic_download_path)
    end
    metron_async_retry(username, password, series_name, dither_fn, attempt,
                       "Metron cover request failed with HTTP " + str(status))
    return
  end

  var response_size = image_client.last_rx
  if response_size <= 0 || response_size > comic_max_source_bytes
    metron_close_client(image_client)
    if path.exists(comic_download_path)
      path.remove(comic_download_path)
    end
    metron_async_retry(username, password, series_name, dither_fn, attempt,
                       "Metron cover response has an invalid size: " + str(response_size))
    return
  end

  var written = image_client.write_file(comic_download_path)
  metron_close_client(image_client)
  if written != response_size
    if path.exists(comic_download_path)
      path.remove(comic_download_path)
    end
    metron_async_retry(username, password, series_name, dither_fn, attempt,
                       "Metron cover was truncated or could not be saved")
    return
  end

  var installed = false
  try
    install_downloaded_cover()
    installed = true
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
    if installed
      if path.exists(comic_source_path)
        path.remove(comic_source_path)
      end
      if path.exists(comic_backup_path)
        if !path.rename(comic_backup_path, comic_source_path)
          raise "io_error", "Could not restore the previous comic image"
        end
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
  var ctx = {
    "username": username,
    "password": password,
    "series_name": series_name,
    "dither_fn": dither_fn,
    "attempt": attempt,
    "seed": int(tasmota.millis()) & 0x7FFFFFFF,
    "random_series": series_name == nil || size(series_name) == 0
  }
  metron_async_fetch_series(ctx)
  return {"status": "pending"}
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
  return metron_async_display(username, password, series_name, dither_fn, 1)
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
  if result.find("status") == "no_suitable_cover"
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
