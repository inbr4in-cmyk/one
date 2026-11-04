# One English — mobile app (students and parents)

Flutter, one codebase for iOS and Android. Talks to the same backend as the web cabinet (`/api/...`, header `X-Client: mobile`).

## Run

```sh
flutter pub get
flutter run --dart-define=OE_API_BASE=https://app.oneenglish.kz
```

Build-time options (`--dart-define`):

- `OE_API_BASE` — backend origin, default `https://app.oneenglish.kz`.
- `OE_PLATFORM=ios|android` — force the iOS or Android look (useful for `flutter build web` previews).

## Push notifications (Firebase)

Firebase files are not in the repo. Without them the app works, push is simply off.

- Android: put `google-services.json` into `android/app/` — the Gradle build applies the Google Services plugin only when it exists.
- iOS: add `GoogleService-Info.plist` to `ios/Runner` in Xcode, enable Push Notifications and Background Modes → Remote notifications, upload the APNs key to Firebase.

After sign-in the app sends `POST /api/auth/devices {platform, token, locale}`; tapping a notification opens its `link` inside the app (`lib/push/links.dart`).

## Release signing (Android)

Release builds are signed with the key described in `android/key.properties`. That file and the keystore are git-ignored and must never be committed; keep the keystore and its passwords in the school's password manager (losing the key means the app can no longer be updated in Google Play, unless Play App Signing is on — then this is the upload key and Google can reset it).

1. Create the keystore once (JDK `keytool`), outside the repository:

   ```sh
   keytool -genkeypair -v -keystore ~/keys/one-english-upload.jks \
     -keyalg RSA -keysize 4096 -validity 10000 -alias upload \
     -dname "CN=One English, O=One English, C=KZ"
   ```

2. Create `android/key.properties` (paths are relative to `android/`, or absolute):

   ```properties
   storeFile=/home/you/keys/one-english-upload.jks
   storePassword=...
   keyAlias=upload
   keyPassword=...
   ```

3. Build: `flutter build appbundle --release` (or `flutter build apk --release`). Check the signature with
   `keytool -printcert -jarfile build/app/outputs/flutter-apk/app-release.apk` — it must show your key, not `CN=Android Debug`.

Without `android/key.properties` the release build falls back to the debug key and Gradle prints a warning: such a build is only for local testing and must not be uploaded. In CI, write `key.properties` and the keystore from secrets before the build and delete them afterwards.

## Screen sizes and text size

The layout is checked by `test/layout_test.dart` on 320×568 and 360×800 at text scale 1.0, 1.3 and 2.0, on phones in landscape and on a 1024×768 tablet (any RenderFlex overflow fails the test). Rules the screens follow:

- The system text size is followed up to 200 %; the tab bar, nav bars, chips, pills, segmented controls, chart labels and the PIN keypad stop at 130 % (`TightText`).
- Names and headings never break inside a word (`WholeWordsText` sets them smaller instead).
- On tablets the content is at most 640 px wide and centred (`ReadableWidth`, `PageList`).
- The PIN screens switch to two columns (text and dots left, keypad right) on short, wide screens.

## Offline demo

`lib/main_demo.dart` is the same app over an in-memory backend (`lib/demo/`): responses recorded from the real API (one parent with two children, one student), dates moved to today, and the main actions (chat, homework, ratings, shop orders, consents, complaints, notifications) applied in memory. Sign in as parent or student from the first screen, or with any phone and code `111111`. No socket, no push, no network.

```sh
tool/build_demo.sh   # → build/web: a static site that works from any sub-path, no external requests
```

## Checks

```sh
flutter analyze
flutter test
```

Strings live in `lib/l10n/app_ru.arb` and `app_kk.arb`, generated from `tool/gen_arb.py` (`python3 tool/gen_arb.py && flutter gen-l10n`). Icons come from `docs/design/mobile.html` via `tool/gen_icons.py`.
