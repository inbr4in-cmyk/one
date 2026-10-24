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

## Checks

```sh
flutter analyze
flutter test
```

Strings live in `lib/l10n/app_ru.arb` and `app_kk.arb`, generated from `tool/gen_arb.py` (`python3 tool/gen_arb.py && flutter gen-l10n`). Icons come from `docs/design/mobile.html` via `tool/gen_icons.py`.
