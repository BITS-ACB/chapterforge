# PRD: Audio-Only Auphonic Integration With User-Owned Credits

**Audience:** Claude / engineering agent implementing the feature  
**Product area:** Audio post-production, podcasting, lecture capture, audiobook cleanup, accessibility transcripts  
**Date:** 2026-06-05  
**Status:** Draft for engineering implementation  

---

## 1. Executive Summary

Build a deep, audio-only integration with Auphonic that allows users to connect their own Auphonic account, upload or reference audio files, configure Auphonic processing options, submit productions, monitor progress, retrieve finished audio/transcript/metadata assets, and publish or export results.

The integration must use **the user’s own Auphonic credits** wherever possible. Users authenticate with Auphonic, purchase recurring or one-time credits directly from Auphonic, and our application shows their available balance before jobs are submitted. This avoids becoming the processor of Auphonic billing in the normal case.

Auphonic supports video workflows, audiograms, and video output, but this product scope is **strictly audio-source only**. We will allow audio inputs, audio outputs, transcripts, subtitles/captions, chapter files, cut lists, stats, waveform images, cover images, and metadata. We will block video inputs and video-oriented outputs unless a future, separate product scope explicitly enables video.

---

## 2. Source Notes for Claude

Use the official Auphonic documentation as the source of truth while implementing. Important verified documentation points:

- Auphonic exposes a REST API for productions, presets, external services, algorithms, webhooks, downloads, and account information: https://auphonic.com/help/api/
- The API has three integration styles: Simple API, JSON API, and CLI. Use REST/JSON for the product backend; use the CLI only as a reference/testing aid: https://auphonic.com/help/api/
- Third-party web/mobile/desktop apps should use OAuth 2.0 where possible: https://auphonic.com/help/api/authentication.html
- `/api/user.json` returns available credit information, including `credits`, `onetime_credits`, `recurring_credits`, `recharge_date`, and `recharge_recurring_credits`: https://auphonic.com/help/api/query.html
- Auphonic bills processing by duration of processed audio, with a 3-minute minimum, and successful processing only; re-runs with the same input and changed settings/metadata are not charged again according to current pricing FAQ: https://auphonic.com/pricing
- Auphonic supports creating productions, uploading files, starting jobs, querying status, publishing, and downloading result files: https://auphonic.com/help/api/details.html and https://auphonic.com/help/api/query.html
- Auphonic supports webhooks for finished processing callbacks: https://auphonic.com/help/api/webhook.html
- Auphonic exposes dynamic API metadata for algorithms, output formats, production statuses, and external service types through `/api/info.json` and related endpoints: https://auphonic.com/help/api/query.html
- Auphonic supports singletrack and multitrack audio processing, including multiple tracks, intros, outros, inserts, offsets, and per-track behavior: https://auphonic.com/help/api/multitrack.html
- Auphonic supports output formats including MP3, AAC/M4A/MP4/M4B, Opus, Ogg Vorbis, FLAC, ALAC, WAV, transcript/subtitle/speech files, stats, chapters, cut lists, waveform images, and cover images. This product must allow only audio-compatible and metadata/accessibility outputs, not video/audiogram outputs: https://auphonic.com/help/api/details.html

---

## 3. Goals

### 3.1 Product Goals

1. Give users a high-quality, accessible, audio-only Auphonic workflow inside our application.
2. Let users pay for Auphonic processing with their own Auphonic credits by connecting their Auphonic account.
3. Provide simple presets for common needs while preserving expert-level control over Auphonic’s algorithms and output settings.
4. Support singletrack and multitrack audio production.
5. Support transcripts, subtitles/captions, shownotes, chapters, metadata, cut lists, waveform images, and processing statistics where available.
6. Make job submission safe by validating audio-only input, checking credits, estimating minimum required credits, and clearly communicating what will happen before the user starts a production.
7. Make the integration future-resilient by querying Auphonic’s dynamic info endpoints rather than hardcoding every algorithm or output option.

### 3.2 Engineering Goals

1. Encapsulate all Auphonic calls behind an internal `AuphonicService` abstraction.
2. Use OAuth 2.0 for user-connected Auphonic accounts. API key support may be available only for admin/internal/testing or advanced single-user desktop mode.
3. Store OAuth tokens encrypted at rest.
4. Implement webhook-first production status updates, with polling fallback.
5. Build an idempotent job system that can recover from process crashes, duplicate webhooks, network failures, and partially completed uploads.
6. Keep all app-side billing/usage records separate from Auphonic’s credit ledger.

---

## 4. Non-Goals

1. Do not build a general video processing workflow.
2. Do not accept video files as source input, even though Auphonic can process video.
3. Do not generate Auphonic video outputs or audiograms in this product scope.
4. Do not resell Auphonic credits unless we have a written white-label/custom-pricing agreement with Auphonic.
5. Do not store raw Auphonic passwords.
6. Do not expose Auphonic tokens to the browser or client app.
7. Do not assume Auphonic plan entitlements from app state alone; use `/api/user.json`, API responses, and error handling.

---

## 5. Billing and Credit Model

### 5.1 Preferred Model: Bring Your Own Auphonic Account

The user connects their Auphonic account through OAuth 2.0. When a production is submitted, Auphonic charges the user’s Auphonic credits directly. Our app only displays the credit balance, estimates required credit duration, and records local usage metadata.

Required user flow:

1. User clicks **Connect Auphonic**.
2. User completes Auphonic OAuth flow.
3. App stores encrypted refresh/access token metadata.
4. App calls `/api/user.json` to display:
   - Total available credits in hours.
   - One-time credits.
   - Recurring credits.
   - Recharge date.
   - Recharge amount.
5. User submits an audio job.
6. App estimates duration and warns if credits appear insufficient.
7. Auphonic processes the job using the user’s Auphonic credits.
8. App stores Auphonic’s returned `used_credits` for the production when the job completes.

### 5.2 Alternative Model: Organization / Team Account

For internal organizations, a business/team Auphonic account may share credits across members. This requires administrative configuration and should be treated as an enterprise mode, not the default.

Implementation requirements:

- Support an app-level Auphonic connection owned by the organization.
- Maintain a local usage ledger per application user.
- Add admin controls for quotas, allowed presets, monthly caps, and approvals.
- Display that jobs are charged to the organization’s Auphonic account, not the user’s personal credits.

### 5.3 Future Model: White Label / Resold Credits

Auphonic advertises white-label/custom pricing possibilities, but this requires direct engagement with Auphonic. Do not implement credit resale as a normal app payment flow until a business agreement exists.

---

## 6. User Personas

### 6.1 Casual Podcast Creator

Wants to upload an MP3/WAV, pick “Podcast Cleanup,” and receive a polished MP3 plus transcript and chapters.

### 6.2 Power User / Audio Producer

Wants control over loudness target, output formats, noise reduction, cut lists, filler removal, intro/outro, multitrack mixing, and publishing targets.

### 6.3 Accessibility-Focused Publisher

Wants transcripts, captions, shownotes, chapters, and searchable audio results.

### 6.4 Organization Admin

Wants standard presets, quota controls, predictable credit usage, logs, and governance.

---

## 7. User Stories

1. As a user, I can connect my Auphonic account so the app can submit jobs using my credits.
2. As a user, I can see my available Auphonic credit balance before I process audio.
3. As a user, I can upload an audio file or reference an audio file by URL.
4. As a user, I can select an Auphonic preset by name or UUID.
5. As a user, I can use a simple workflow without understanding every algorithm setting.
6. As a power user, I can configure all supported Auphonic audio algorithm settings exposed by `/api/info/algorithms.json`.
7. As a user, I can request MP3, AAC/M4A, Opus, Ogg, FLAC, ALAC, WAV, and other audio-compatible outputs supported by Auphonic.
8. As a user, I can request transcripts, subtitles, speech JSON/XML, stats, chapters, cut lists, waveform images, and cover image outputs.
9. As a user, I can create multitrack productions with multiple audio tracks.
10. As a user, I can add intro, outro, and insert audio files at configured offsets.
11. As a user, I can monitor processing progress without manually refreshing.
12. As a user, I can download result files from the app.
13. As a user, I can publish processed results to allowed audio-compatible external services when configured.
14. As an admin, I can restrict allowed output formats, max durations, and advanced features.
15. As an admin, I can audit submitted jobs, credits consumed, users, timestamps, and errors.

---

## 8. Functional Requirements

## 8.1 Auphonic Account Connection

### Requirements

- Implement Auphonic OAuth 2.0 web-app authentication.
- Store tokens encrypted at rest.
- Refresh tokens as needed.
- Provide a **Disconnect Auphonic** action.
- On disconnect, remove locally stored tokens and mark active jobs as inaccessible unless the user reconnects.
- Never store Auphonic username/password.
- Provide optional API key mode only behind an admin/developer flag.

### Acceptance Criteria

- User can connect Auphonic and return to app successfully.
- App can call `/api/user.json` after connection.
- Token is never sent to browser/client logs.
- Disconnect removes stored credentials.

---

## 8.2 Credit Display and Preflight Estimate

### Requirements

- Call `/api/user.json` before showing production submit UI and before final submission.
- Display:
  - Total credits.
  - One-time credits.
  - Recurring credits.
  - Recharge date.
  - Recharge recurring amount.
- Estimate required credits from audio duration.
- Apply Auphonic’s documented 3-minute minimum for short productions.
- For multitrack jobs, estimate based on expected output duration, not sum of all parallel track lengths.
- Include intros/outros/inserts in estimate when possible.
- Warn but do not falsely guarantee exact billing.
- After completion, read `used_credits` from production details and store actual usage.

### Acceptance Criteria

- A user sees a clear warning when estimated duration exceeds visible credits.
- A 90-second audio file shows a 3-minute minimum estimate.
- A one-hour, four-track multitrack production estimates approximately one hour, not four hours, assuming parallel tracks.
- Completed jobs show actual `used_credits` where Auphonic returns it.

---

## 8.3 Audio-Only Source Validation

### Requirements

Allowed input source types:

1. Local browser upload to app backend.
2. Server-side file path from app storage.
3. Public HTTPS URL.
4. Auphonic external service file reference, when the connected user has that service configured.
5. Multiple local/URL/external-service audio files for multitrack.
6. Audio-only intro/outro/insert files.

Validation rules:

- Allow only audio file extensions and MIME types.
- Inspect file magic where possible.
- Use `ffprobe` or equivalent server-side inspection to confirm at least one audio stream and zero video streams.
- Reject files with video streams.
- Reject unknown/unsafe container types.
- Reject files above configured duration, size, or user/admin limits.
- For remote URLs, fetch only metadata first when possible. If metadata is inconclusive, download to a quarantine/staging location and inspect before forwarding to Auphonic.
- For external service listings, filter the returned file list to audio extensions only before showing options to the user.

Recommended audio allowlist:

- `.mp2`, `.mp3`, `.m4a`, `.m4b`, `.aac`, `.wav`, `.wave`, `.ogg`, `.oga`, `.opus`, `.flac`, `.alac`, `.aif`, `.aiff`, `.aifc`, `.au`, `.caf`, `.wma`, `.ac3`, `.eac3`, `.ape`, `.spx`, `.vox`, `.voc`, `.snd`, `.tta`, `.w64`

Explicitly blocked examples:

- `.mp4`, `.m4v`, `.mov`, `.avi`, `.mkv`, `.webm`, `.flv`, `.mpeg`, `.mpg`, `.ts`, `.vob`, `.ogv`, `.mxf`, and any file containing a video stream.

Important nuance:

- `.mp4` can contain audio-only AAC, but this product should avoid ambiguous video-capable containers by default unless server-side stream inspection confirms audio-only and admin policy allows it.

### Acceptance Criteria

- Uploading an MP3 passes validation.
- Uploading an MP4 with video fails validation.
- A remote URL with a misleading extension is inspected and blocked if it contains video.
- A multitrack job cannot include any video file.

---

## 8.4 Production Creation Modes

Support two production creation paths.

### 8.4.1 Simple Mode

Use Auphonic’s Simple API only for simple jobs where a preset, metadata, audio file, and action can be submitted in one multipart request.

Use cases:

- Quick upload and start.
- Simple batch processing.
- Minimal UI.

### 8.4.2 Full JSON Mode

Use the JSON API for all rich workflows.

Use cases:

- Full algorithm control.
- Multiple output files.
- Multitrack.
- Intro/outro/insert audio.
- Speech recognition.
- Chapters and metadata.
- Webhooks.
- Review-before-publish.
- Publishing to external services.

Default implementation should use JSON mode for consistency, except for explicitly simple internal scripts.

### Acceptance Criteria

- The backend can create a production, upload files when required, start it, and track it to completion.
- The same internal job model can represent Simple API and JSON API submissions.

---

## 8.5 Presets

### Requirements

- List user presets through `/api/presets.json`.
- Support `minimal_data=1` for faster lists.
- Allow presets to be referenced by UUID or by name.
- Support Auphonic-provided presets, user presets, and all presets when supported by API filters.
- Allow users to create/edit/delete presets where exposed by the API and permitted by account policy.
- Allow app-level recommended presets that map to Auphonic JSON payloads.
- Provide a “duplicate preset into app template” feature for safer editing.

### Preset UX

Provide a default preset library:

1. **Podcast Cleanup**: loudness target around podcast norms, leveling, filtering, denoise automatic, optional filler/cough/silence cutting disabled by default.
2. **Podcast Cleanup + Transcript**: same as above plus transcript/subtitle outputs and shownotes if the account supports it.
3. **Audiobook / ACX Draft**: RMS-based loudness method where appropriate, careful denoise, high-quality WAV/FLAC output.
4. **Lecture Cleanup**: voice-focused denoise, leveler, captions/transcript outputs.
5. **Meeting / Interview Multitrack**: host/guest track layout with adaptive processing and optional transcript.
6. **Archive Master**: FLAC/WAV output, minimal cutting, metadata and stats.

### Acceptance Criteria

- User can select a preset by human-readable name.
- App correctly handles duplicate preset names using Auphonic’s documented priority behavior or by using UUIDs once selected.
- Advanced users can inspect the resolved JSON before submission.

---

## 8.6 Audio Algorithm Support

### Requirements

- Fetch `/api/info/algorithms.json` and use it to drive supported fields, labels, options, defaults, dependencies, and validation.
- Cache algorithm schema with a refresh schedule.
- Provide friendly UI groups, but preserve access to all API-supported fields.
- Include at least these algorithm families:
  - Adaptive leveler.
  - Loudness normalization.
  - Loudness target.
  - Max peak.
  - Loudness method including program/dialog/RMS where available.
  - Noise reduction.
  - Noise reduction amount.
  - Dehum and hum reduction options where available.
  - Reverb reduction/deverb where available.
  - Filtering, AutoEQ, bandwidth extension where available.
  - Compressor and separate speech/music parameters where available.
  - Music/speech classifier options.
  - Music gain.
  - Broadcast controls such as Max LRA, Max S, Max M where available.
  - Automatic cutting: silence, filler words, coughs, music.
  - Cut modes: apply cuts, export uncut audio, set cuts to silence.
  - Manual cuts.
  - Denoise segments.
  - Fade in/out time.

### UX Requirements

- Offer “Basic” and “Advanced” modes.
- Basic mode hides dangerous or confusing controls.
- Advanced mode exposes all fetched algorithm settings.
- Provide screen-reader-friendly descriptions and warnings.
- Provide default tooltips from Auphonic descriptions when available.

### Acceptance Criteria

- When Auphonic adds a new algorithm option, the app can surface it after schema refresh without a code release, unless admin policy blocks it.
- Invalid combinations are blocked client-side and server-side.
- If Auphonic rejects a submitted algorithm payload, the app shows the API error with actionable context.

---

## 8.7 Output Files

### Requirements

Fetch `/api/info/output_files.json` and expose audio-compatible and metadata/accessibility outputs.

Allowed output categories:

1. Audio:
   - MP3.
   - MP3 VBR.
   - AAC/M4A/M4B where audio-only.
   - Opus.
   - Ogg Vorbis.
   - FLAC.
   - ALAC.
   - WAV 16-bit PCM.
   - WAV 24-bit PCM.
2. Accessibility / metadata / data:
   - Transcript HTML/TXT.
   - Subtitle SRT/WebVTT.
   - Speech JSON/XML.
   - Chapters TXT.
   - Podlove Simple Chapters XML/PSC.
   - Cut lists.
   - Audio processing stats TXT/JSON/YAML.
   - Waveform image.
   - Cover image copy.
   - Production description JSON/XML/YAML.
   - Original input file only if admin policy allows retaining/distributing originals.

Blocked output categories:

- Video output.
- Audiogram / waveform video output.
- Any YouTube-oriented generated video output.
- Any output that requires or implies a video stream.

Output controls:

- Bitrate.
- File extension/ending.
- Filename.
- Suffix.
- Output basename.
- Mono mixdown.
- Split on chapters.
- Per-output outgoing service routing where allowed.

### Acceptance Criteria

- User can request multiple audio outputs from one production.
- User can produce both an MP3 and a FLAC without extra Auphonic credit impact beyond processed duration, consistent with Auphonic’s billing documentation.
- User cannot select `video` or `audiogram` output in this product mode.
- User can download each result file from our app.

---

## 8.8 Speech Recognition, Transcripts, Captions, and Shownotes

### Requirements

- Support Auphonic Whisper speech recognition where available by sending language and optional keywords without external speech service UUID.
- Support external speech recognition service UUIDs for users who have configured Google Cloud Speech, Amazon Transcribe, Speechmatics, or other Auphonic-supported services.
- Support language selection.
- Support keyword hints.
- Support output formats:
  - Transcript HTML.
  - Transcript TXT.
  - Subtitle SRT.
  - Subtitle WebVTT.
  - Speech JSON.
  - Speech XML.
- Support automatic shownotes and generated chapters where available to paying users.
- Store transcript assets in the app’s result model.
- Provide copy/export actions for show notes, chapters, transcript text, and captions.

### Acceptance Criteria

- A completed production can show a transcript download when requested.
- If shownotes are requested but the user’s account is not eligible, the app handles the Auphonic error and explains the limitation.
- Captions are downloadable as SRT and WebVTT where Auphonic returns them.

---

## 8.9 Chapters and Metadata

### Requirements

Support metadata fields exposed by Auphonic, including at minimum:

- Title.
- Artist.
- Album.
- Track.
- Subtitle.
- Summary/description.
- Genre.
- Year.
- Publisher.
- URL.
- License.
- License URL.
- Tags.
- Append chapters flag.
- Location metadata if needed and privacy policy allows it.

Support chapters:

- Manual chapter entry.
- Import chapter text.
- URL-based chapter file.
- Chapter title.
- Chapter URL.
- Chapter image where allowed.
- Export chapter files.
- Automatically generated chapters from shownotes when available.

### Audio-only policy

Cover images and chapter images are allowed as metadata assets. They must not enable video output generation in this product scope.

### Acceptance Criteria

- User can add chapters and receive audio files with embedded chapters where the selected format supports them.
- User can export chapter files.
- Metadata appears in supported output files.

---

## 8.10 Multitrack Productions

### Requirements

Support multitrack audio-only productions.

Capabilities:

- Add multiple track files.
- Name tracks.
- Upload local track audio.
- Reference remote/external-service track audio.
- Configure per-track settings where API supports them.
- Configure pan/gain/background behavior where available.
- Support parallel host/guest/music tracks.
- Support intro/outro/insert files separately from multitrack tracks.
- Support per-track transcript speaker naming where available from Auphonic output.

Validation:

- Every track must pass audio-only validation.
- Tracks should have compatible duration expectations, but do not require exact same length unless Auphonic/API does.
- Reject files with video streams.

### Acceptance Criteria

- User can create a two-track host/guest production.
- User can create a host/guest/music production.
- User can download a final mixed audio output.
- User can request individual track outputs only if Auphonic/API supports them and output remains audio-only.

---

## 8.11 Intro, Outro, and Inserts

### Requirements

- Support one or more intro files.
- Support one or more outro files.
- Support insert files at offsets in seconds.
- Support overlap/crossfade offsets where Auphonic supports them.
- Validate all intro/outro/insert files as audio-only.
- Clearly communicate that inserts should be prepared/processed already, because Auphonic normalizes them but does not fully process them like the main audio.

### Acceptance Criteria

- User can add an intro with a 2-second overlap.
- User can add an outro with a 3-second overlap.
- User can insert an audio segment at a configured time offset.
- Non-audio insert uploads are rejected.

---

## 8.12 External Services and Publishing

### Requirements

- List connected Auphonic external services through `/api/services.json`.
- List files on a selected service through `/api/service/{uuid}/ls.json`.
- Filter listed files to audio-only extensions.
- Allow incoming file selection from allowed external services.
- Allow outgoing publishing only to audio-compatible destinations and app-approved services.
- Block YouTube/video destinations by default in audio-only mode.
- Support `review_before_publishing` where the user wants to inspect outputs before final publishing.
- Support the `publish` action after review.

### Allowed-by-default external service categories

- Dropbox.
- Google Drive.
- OneDrive.
- Amazon S3.
- FTP/SFTP/WebDAV.
- Podcast/audio hosting services where Auphonic supports audio publication and the selected output is audio-only.
- SoundCloud where the user has configured it and output is audio-only.

### Blocked-by-default categories

- YouTube.
- Video-oriented destinations.
- Any destination requiring generated video output.

### Acceptance Criteria

- User can select an MP3 from Dropbox as input if connected in Auphonic.
- User cannot select a `.mov` or `.mp4` video from Dropbox.
- User can publish an audio output to an allowed audio destination.
- User can choose review-before-publish and manually trigger publishing later.

---

## 8.13 Production Status, Webhooks, and Polling

### Requirements

- Include a per-production webhook URL when creating productions.
- Webhook endpoint must verify that the callback matches a known production UUID and user/job.
- Webhook handler must be idempotent.
- Use polling fallback for jobs that do not receive a webhook.
- Use exponential backoff.
- Avoid very frequent status polling because Auphonic recommends webhooks for frequent status updates.
- Store status code, status string, error messages, warnings, and change time.
- Provide user-visible status states:
  - Draft/saved.
  - Uploading.
  - Ready to start.
  - Queued/processing.
  - Done.
  - Error.
  - Needs review before publish.
  - Published.
  - Deleted/canceled where applicable.

### Acceptance Criteria

- Duplicate webhook events do not create duplicate downloads or state corruption.
- If a webhook is missed, polling eventually updates job status.
- User sees errors from Auphonic in a useful, accessible way.

---

## 8.14 Downloads and Result Storage

### Requirements

- On completion, fetch production details.
- Read all returned output files.
- Present download options for each allowed result file.
- Follow redirects when downloading Auphonic result files.
- Store files according to app retention policy.
- Allow user to re-fetch from Auphonic if local retention expired and token is still valid.
- Include result metadata:
  - Filename.
  - Format.
  - Bitrate.
  - Size.
  - Download URL source.
  - Auphonic production UUID.
  - Created/completed timestamps.

### Acceptance Criteria

- User can download MP3, FLAC, transcript, captions, stats, cut lists, and chapter files when produced.
- App does not display blocked video/audiogram outputs even if accidentally returned.
- Downloads work with Auphonic redirect behavior.

---

## 8.15 Job History and Re-Runs

### Requirements

- Show a job history list per user.
- Include title, status, duration, credits used, created time, completed time, preset, outputs, and source type.
- Support re-running with same input and adjusted settings where Auphonic allows it without additional credit charge.
- Make clear that changing input files or creating a new production can trigger new charges.
- Support “duplicate job as new production” with explicit charge warning.

### Acceptance Criteria

- User can find prior processed audio.
- User can view exact settings submitted to Auphonic.
- User receives a warning before creating a new chargeable production from an old job.

---

## 9. Data Model

Use these tables/collections as a starting point.

### 9.1 `auphonic_connections`

- `id`
- `user_id`
- `auphonic_user_id`
- `auphonic_username`
- `auphonic_email`
- `oauth_access_token_encrypted`
- `oauth_refresh_token_encrypted`
- `token_expires_at`
- `connection_status`
- `last_user_sync_at`
- `created_at`
- `updated_at`

### 9.2 `auphonic_credit_snapshots`

- `id`
- `user_id`
- `connection_id`
- `credits_hours`
- `onetime_credits_hours`
- `recurring_credits_hours`
- `recharge_date`
- `recharge_recurring_credits_hours`
- `raw_response_json`
- `created_at`

### 9.3 `audio_assets`

- `id`
- `user_id`
- `source_type` (`upload`, `url`, `external_service`, `app_storage`)
- `original_filename`
- `content_type`
- `extension`
- `size_bytes`
- `duration_seconds`
- `has_audio_stream`
- `has_video_stream`
- `audio_codec`
- `sample_rate`
- `channels`
- `validation_status`
- `storage_uri`
- `remote_url`
- `external_service_uuid`
- `external_service_path`
- `created_at`

### 9.4 `auphonic_jobs`

- `id`
- `user_id`
- `connection_id`
- `auphonic_production_uuid`
- `title`
- `mode` (`simple`, `json`)
- `is_multitrack`
- `status_code`
- `status_string`
- `app_status`
- `estimated_credits_hours`
- `used_credits_hours`
- `source_asset_id`
- `preset_uuid`
- `preset_name`
- `request_json`
- `response_json`
- `error_message`
- `warning_message`
- `review_before_publishing`
- `webhook_secret`
- `created_at`
- `started_at`
- `completed_at`
- `updated_at`

### 9.5 `auphonic_job_tracks`

- `id`
- `job_id`
- `asset_id`
- `track_id`
- `track_name`
- `role` (`track`, `intro`, `outro`, `insert`)
- `offset_seconds`
- `settings_json`
- `created_at`

### 9.6 `auphonic_outputs`

- `id`
- `job_id`
- `format`
- `ending`
- `filename`
- `bitrate`
- `size_bytes`
- `download_url_encrypted_or_signed`
- `local_storage_uri`
- `is_allowed_audio_mode`
- `output_type` (`audio`, `transcript`, `subtitle`, `speech-data`, `stats`, `chapters`, `cut-list`, `image`, `description`)
- `created_at`

### 9.7 `auphonic_schema_cache`

- `id`
- `schema_type` (`algorithms`, `output_files`, `service_types`, `production_status`, `info_all`)
- `schema_json`
- `fetched_at`
- `expires_at`

---

## 10. API Integration Map

### 10.1 Authentication

- OAuth 2.0 for third-party app users.
- API key only for internal/admin/dev or user-owned desktop mode.

### 10.2 Account and Credits

- `GET /api/user.json`

Use for:

- Account identity.
- Credit balance.
- Recharge information.
- Low-credit UX.

### 10.3 Info / Dynamic Capabilities

- `GET /api/info.json`
- `GET /api/info/algorithms.json`
- `GET /api/info/output_files.json`
- `GET /api/info/service_types.json`
- `GET /api/info/production_status.json`

Use for:

- Dynamic UI.
- Validation.
- Future-proofing.
- Admin allowlists.

### 10.4 Productions

- `POST /api/productions.json`
- `POST /api/production/{uuid}.json`
- `POST /api/production/{uuid}/upload.json`
- `POST /api/production/{uuid}/start.json`
- `GET /api/production/{uuid}.json`
- `GET /api/production/{uuid}/status.json`
- `POST /api/production/{uuid}/publish.json`
- `DELETE /api/production/{uuid}.json` where supported/verified in the OpenAPI reference.

Use for:

- Create.
- Update.
- Upload.
- Start.
- Read details.
- Monitor status.
- Publish.
- Delete/cleanup.

### 10.5 Presets

- `GET /api/presets.json`
- `GET /api/preset/{uuid}.json`
- `POST /api/presets.json`
- `POST /api/preset/{uuid}.json`
- Preset command endpoints where supported: metadata, output_files, outgoing_services, multi_input_files, algorithms, speech_recognition, upload.

### 10.6 External Services

- `GET /api/services.json`
- `GET /api/service/{uuid}/ls.json`
- `GET /api/info/service_types.json`

Use for:

- Incoming audio selection.
- Outgoing publishing.
- Service capability display.

### 10.7 Webhooks

- Set `webhook` when creating/updating production or preset.
- App endpoint example: `POST /webhooks/auphonic/{jobId}/{secret}`

Use for:

- Completion callbacks.
- Status sync.
- Result ingestion.

---

## 11. Example Internal Production Payloads

### 11.1 Singletrack Podcast Cleanup

```json
{
  "input_file": "https://example.com/audio/episode-42.wav",
  "metadata": {
    "title": "Episode 42 - Interview",
    "artist": "Example Podcast",
    "album": "Example Podcast",
    "genre": "Podcast",
    "summary": "Interview episode."
  },
  "output_basename": "episode-42-processed",
  "output_files": [
    { "format": "mp3", "bitrate": "128", "ending": "mp3" },
    { "format": "flac" },
    { "format": "stats", "ending": "json" }
  ],
  "algorithms": {
    "leveler": true,
    "normloudness": true,
    "loudnesstarget": -16,
    "maxpeak": -1,
    "filtering": true,
    "denoise": true,
    "denoiseamount": 0,
    "silence_cutter": false,
    "filler_cutter": false,
    "cough_cutter": false
  },
  "webhook": "https://app.example.com/webhooks/auphonic/job_123/secret",
  "action": "start"
}
```

### 11.2 Transcript and Captions

```json
{
  "speech_recognition": {
    "language": "en",
    "keywords": ["Auphonic", "accessibility", "podcast"],
    "shownotes": true,
    "shownotes_summary_example": "A concise episode summary written for podcast show notes."
  },
  "output_files": [
    { "format": "transcript", "ending": "html" },
    { "format": "transcript", "ending": "txt" },
    { "format": "subtitle", "ending": "srt" },
    { "format": "subtitle", "ending": "webvtt" },
    { "format": "speech", "ending": "json" }
  ]
}
```

### 11.3 Intro, Outro, and Insert

```json
{
  "multi_input_files": [
    {
      "input_file": "https://example.com/audio/intro.wav",
      "type": "intro",
      "offset": 2.0
    },
    {
      "input_file": "https://example.com/audio/outro.wav",
      "type": "outro",
      "offset": 3.0
    },
    {
      "input_file": "https://example.com/audio/sponsor.wav",
      "type": "insert",
      "offset": 600.0
    }
  ]
}
```

### 11.4 Manual Cuts and Denoise Segments

```json
{
  "cuts": [
    [12.2, 15.8],
    [240.0, 245.5]
  ],
  "algorithms": {
    "denoise": true,
    "segments": [
      { "start": 0, "stop": 120, "denoisemethod": "speech", "denoiseamount": 6 },
      { "start": 120, "stop": 300, "denoisemethod": "music", "denoiseamount": 3 },
      { "start": 300, "stop": 900, "denoisemethod": "speech", "deverbamount": 12 }
    ]
  }
}
```

---

## 12. UX Requirements

### 12.1 Main Screens

1. **Connect Auphonic**
   - Connection status.
   - Credit balance.
   - Link to Auphonic pricing/account page.

2. **New Audio Production**
   - Source selection.
   - Audio validation status.
   - Duration and credit estimate.
   - Preset selection.
   - Basic/Advanced toggle.
   - Output selection.
   - Transcript/captions options.
   - Submit button with final charge warning.

3. **Advanced Settings**
   - Algorithm groups.
   - Output formats.
   - Chapters.
   - Metadata.
   - Intro/outro/inserts.
   - Multitrack builder.
   - External publishing.

4. **Job Status**
   - Status text.
   - Warnings/errors.
   - Auphonic status page link if available.
   - Progress messaging.
   - Cancel/delete action where safe.

5. **Results**
   - Audio player for final audio.
   - Download buttons.
   - Transcript viewer.
   - Captions download.
   - Chapters and shownotes.
   - Stats and cut lists.
   - Publish button when review-before-publishing is enabled.

6. **History**
   - Searchable/sortable job table.
   - Filter by status, date, preset, output type.
   - Duplicate/re-run controls with charge warning.

### 12.2 Accessibility Requirements

- All forms must be keyboard accessible.
- All controls must have visible labels and programmatic names.
- Dynamic status updates must use polite live regions.
- Errors must be associated with fields.
- Tables must have meaningful headers.
- Audio player controls must be screen-reader accessible.
- Transcript and chapters must be navigable by headings/landmarks.
- Do not rely on color alone to show errors, warnings, status, or credit sufficiency.

---

## 13. Admin and Policy Controls

Admin settings:

- Enable/disable Auphonic integration globally.
- Require OAuth vs allow API keys.
- Set maximum upload size.
- Set maximum duration per job.
- Set maximum jobs per user per day/month.
- Set allowed output formats.
- Enable/disable advanced algorithm editing.
- Enable/disable multitrack.
- Enable/disable external-service publishing.
- Enable/disable speech recognition/shownotes.
- Enable/disable local retention of result files.
- Set retention period.
- Configure audio-only strictness.
- Configure enterprise/team-account mode.

---

## 14. Security Requirements

- Encrypt OAuth tokens and API keys at rest.
- Do not log tokens or signed download URLs.
- Use CSRF protection for OAuth and all state-changing app routes.
- Use a nonce/state parameter in OAuth flow.
- Validate webhook UUIDs against known jobs.
- Use unguessable webhook secrets in callback URLs.
- Sanitize all filenames.
- Store uploads outside web root.
- Virus/malware scan uploaded files where infrastructure supports it.
- Enforce content-type and file magic validation.
- Prevent SSRF when accepting remote URLs:
  - Only allow HTTPS by default.
  - Block localhost, private IP ranges, link-local addresses, and metadata endpoints.
  - Follow redirects safely with a max redirect count.
- Rate-limit submissions.
- Rate-limit webhook endpoint.
- Use least-privilege storage permissions.

---

## 15. Error Handling

Common errors and expected user messages:

1. **Not connected to Auphonic**  
   “Connect your Auphonic account before processing audio.”

2. **Insufficient credits**  
   “This job appears to need about X minutes. Your Auphonic account currently shows Y minutes available. Add credits in Auphonic or choose a shorter file.”

3. **Blocked video source**  
   “This product currently accepts audio-only sources. The selected file contains a video stream.”

4. **Auphonic rejected setting**  
   “Auphonic did not accept one or more processing settings. Review the highlighted settings and try again.”

5. **Processing failed**  
   Show Auphonic `error_message` and preserve logs for support.

6. **Webhook missed**  
   Do not show this to user unless job remains stale. Use polling fallback.

7. **Download expired or inaccessible**  
   “Reconnect Auphonic or re-open the production in Auphonic to retrieve this result.”

---

## 16. Implementation Plan for Claude

### Phase 1: Auphonic Client Library

Build `AuphonicClient` with methods:

- `getUser()`
- `getInfo()`
- `getAlgorithms()`
- `getOutputFormats()`
- `getProductionStatuses()`
- `listPresets(options)`
- `getPreset(uuid)`
- `createPreset(payload)`
- `updatePreset(uuid, payload)`
- `listServices()`
- `listServiceFiles(serviceUuid)`
- `createProduction(payload)`
- `updateProduction(uuid, payload)`
- `uploadProductionFiles(uuid, files)`
- `startProduction(uuid)`
- `getProduction(uuid)`
- `getProductionStatus(uuid)`
- `publishProduction(uuid)`
- `downloadResult(urlOrOutputFile)`

All methods must:

- Use authenticated requests.
- Handle JSON errors consistently.
- Never log secrets.
- Return typed result objects.

### Phase 2: OAuth Connection

- Add OAuth start/callback routes.
- Persist encrypted tokens.
- Add token refresh.
- Add disconnect.
- Add account/credit sync.

### Phase 3: Schema Sync

- Fetch `/api/info.json`.
- Store algorithm/output/service/status schema.
- Build allowlist filtering for audio-only mode.
- Add nightly/background refresh.
- Add manual admin refresh.

### Phase 4: Audio Validation Pipeline

- Implement upload staging.
- Inspect file extension, MIME, and magic.
- Run `ffprobe` or equivalent.
- Store duration/codecs/streams.
- Block video streams.
- Implement remote URL validation with SSRF protection.
- Implement external-service file filtering.

### Phase 5: Production Builder

- Build internal normalized production request model.
- Add conversion from UI model to Auphonic JSON payload.
- Add credit estimate.
- Add final submit confirmation.
- Submit production as saved or start immediately.
- Store request/response.

### Phase 6: Status and Results

- Add webhook endpoint.
- Add polling fallback.
- Fetch production details on completion.
- Persist outputs.
- Download and store allowed output files.
- Filter blocked outputs.
- Display result screen.

### Phase 7: Rich Features

- Preset management.
- Multitrack builder.
- Intro/outro/insert UI.
- Chapters and metadata UI.
- Speech recognition and shownotes UI.
- External publishing with review-before-publish.
- Re-run/duplicate workflows.

### Phase 8: Admin, Audit, and Hardening

- Add admin policy controls.
- Add usage ledger and reports.
- Add alerting for job failures.
- Add structured logs without secrets.
- Add integration tests with mocked Auphonic API.
- Add a sandbox/test account workflow.

---

## 17. Testing Requirements

### Unit Tests

- Token encryption/decryption.
- OAuth state validation.
- Credit estimate calculation.
- Audio-only allowlist.
- Output allowlist.
- Auphonic payload generation.
- Error mapping.

### Integration Tests

- Connect account.
- Fetch user credits.
- Fetch info schema.
- Create saved production.
- Upload file.
- Start production.
- Process webhook.
- Fetch/download result files.
- Handle Auphonic error response.

### Security Tests

- SSRF blocked for remote URLs.
- Token not logged.
- Webhook secret required.
- Video stream blocked even with audio extension.
- Path traversal blocked in filenames.

### Accessibility Tests

- Keyboard-only production creation.
- Screen reader labels for every control.
- Live region status updates.
- Error summaries.
- Results table headings.

---

## 18. Open Questions

1. Do we need Auphonic to whitelist our OAuth app for any advanced external-service/publishing integration?
2. Will we support API key mode for desktop users, or only OAuth?
3. Should organization/team-account mode be in V1 or V2?
4. What is the maximum audio duration/file size we want to allow?
5. Should app retain processed outputs permanently, temporarily, or not at all?
6. Should transcript editing happen inside our app, or should we link to Auphonic’s transcript editor/result page?
7. Do we need a formal white-label/custom pricing relationship with Auphonic for any planned product packaging?

---

## 19. Definition of Done

The feature is complete when:

1. Users can connect Auphonic through OAuth.
2. Users can see Auphonic credit balance.
3. Users can submit audio-only singletrack productions.
4. Users can submit audio-only multitrack productions.
5. Users can configure presets, algorithms, metadata, chapters, outputs, transcripts, and allowed publishing.
6. Video inputs and video outputs are blocked.
7. Webhooks and polling reliably update status.
8. Result files are downloadable from the app.
9. Actual used credits are shown after completion when Auphonic returns them.
10. Admins can restrict formats, duration, advanced controls, and external publishing.
11. All major flows pass keyboard and screen reader testing.
12. All secrets are encrypted and omitted from logs.

