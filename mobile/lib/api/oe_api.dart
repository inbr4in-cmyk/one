import 'dart:typed_data';

import 'api_client.dart';
import 'models.dart';

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// Typed calls to the endpoints the student/parent app uses. Business rules stay on the server.
class OeApi {
  OeApi(this.client);
  final ApiClient client;

  // ---------- auth ----------
  Future<void> otpRequest(String phone) => client.postPublic('/auth/otp/request', {'phone': phone});

  Future<void> otpVerify(String phone, String code) async {
    final r = (await client.postPublic('/auth/otp/verify', {'phone': phone, 'code': code})) as Json;
    await client.setTokens(r['access_token'] as String, r['refresh_token'] as String?);
  }

  Future<AuthMe> authMe() async => AuthMe.fromJson((await client.get('/auth/me')) as Json);
  Future<void> logout() => client.post('/auth/logout');
  Future<void> registerDevice(String platform, String token, String locale) =>
      client.post('/auth/devices', {'platform': platform, 'token': token, 'locale': locale});
  Future<void> unregisterDevice(String token) => client.delete('/auth/devices/${Uri.encodeComponent(token)}');
  Future<List<SessionInfo>> sessions() async => parseList(await client.get('/auth/sessions'), SessionInfo.fromJson);
  Future<void> endSession(int id) => client.delete('/auth/sessions/$id');
  Future<void> endOtherSessions() => client.delete('/auth/sessions');

  // ---------- portal ----------
  Future<PortalMe> portalMe() async => PortalMe.fromJson((await client.get('/portal/me')) as Json);

  Future<List<Lesson>> schedule(int studentId, {DateTime? start, int days = 14}) async => parseList(
      await client.get('/portal/students/$studentId/schedule',
          query: {'start': start == null ? null : _iso(start), 'days': days}),
      Lesson.fromJson);

  Future<Attendance> attendance(int studentId) async =>
      Attendance.fromJson((await client.get('/portal/students/$studentId/attendance')) as Json);

  Future<List<Homework>> homework(int studentId) async =>
      parseList(await client.get('/portal/students/$studentId/homework'), Homework.fromJson);

  Future<void> submitHomework(int homeworkId, int studentId, {String? answer, String? fileKey}) =>
      client.post('/portal/homework/$homeworkId/submit', {'student_id': studentId, 'answer': answer, 'file_key': fileKey});

  Future<Payments> payments(int studentId) async =>
      Payments.fromJson((await client.get('/portal/students/$studentId/payments')) as Json);

  Future<StudentBooks> books(int studentId) async =>
      StudentBooks.fromJson((await client.get('/students/$studentId/books')) as Json);

  Future<List<TestResult>> tests(int studentId) async =>
      parseList(await client.get('/portal/students/$studentId/tests'), TestResult.fromJson);

  Future<void> rateLesson(int lessonId, int studentId, int stars) =>
      client.post('/portal/lessons/$lessonId/rate', {'student_id': studentId, 'stars': stars});

  // ---------- chats ----------
  Future<List<Chat>> chats() async => parseList(await client.get('/chats'), Chat.fromJson);
  Future<List<ChatUser>> contacts({String? q}) async =>
      parseList(await client.get('/chats/contacts', query: {'q': q}), ChatUser.fromJson);
  Future<Chat> openDirect(int userId) async => Chat.fromJson((await client.post('/chats/direct', {'user_id': userId})) as Json);
  Future<List<ChatMessage>> messages(int chatId, {int? beforeId, int? afterId}) async => parseList(
      await client.get('/chats/$chatId/messages', query: {'before_id': beforeId, 'after_id': afterId}),
      ChatMessage.fromJson);
  Future<ChatMessage> send(int chatId, {String? text, String? fileKey, String? fileName, String kind = 'text'}) async =>
      ChatMessage.fromJson((await client.post('/chats/$chatId/messages',
          {'text': text, 'file_key': fileKey, 'file_name': fileName, 'kind': kind})) as Json);
  Future<void> markRead(int chatId) => client.post('/chats/$chatId/read');
  Future<List<ChatMessage>> pinned(int chatId) async =>
      parseList(await client.get('/chats/$chatId/pinned'), ChatMessage.fromJson);
  Future<void> hideMessage(int messageId) => client.delete('/chat-messages/$messageId');

  Future<UploadedFile> upload(Uint8List bytes, String name, String contentType) async =>
      UploadedFile.fromJson(await client.upload(bytes, name, contentType));

  // ---------- notifications ----------
  Future<(int, List<Notice>)> notifications() async {
    final r = (await client.get('/notifications', query: {'limit': 50})) as Json;
    return ((r['unread'] as num?)?.toInt() ?? 0, parseList(r['items'], Notice.fromJson));
  }

  Future<void> readAllNotifications() => client.post('/notifications/read-all');
  Future<Json> counters() async => (await client.get('/counters')) as Json;
  Future<String> wsTicket() async => ((await client.post('/ws/ticket')) as Json)['ticket'] as String;

  // ---------- coins & shop ----------
  Future<CoinHistory> coins(int studentId) async =>
      CoinHistory.fromJson((await client.get('/students/$studentId/coins')) as Json);
  Future<List<LeaderRow>> leaderboard({int? groupId, int? branchId}) async => parseList(
      await client.get('/coins/top', query: {'group_id': groupId, 'branch_id': branchId, 'limit': 20}),
      LeaderRow.fromJson);
  Future<List<ShopItem>> shopItems(int branchId) async =>
      parseList(await client.get('/shop/items', query: {'branch_id': branchId}), ShopItem.fromJson);
  Future<int> order(int studentId, int itemId) async =>
      (((await client.post('/shop/orders', {'student_id': studentId, 'item_id': itemId})) as Json)['balance'] as num)
          .toInt();
  Future<List<ShopOrder>> orders(int studentId) async =>
      parseList(await client.get('/shop/orders', query: {'student_id': studentId}), ShopOrder.fromJson);
  Future<void> cancelOrder(int orderId) => client.post('/shop/orders/$orderId/status', {'status': 'cancelled'});

  // ---------- compliance ----------
  /// null when the school hasn't published this document yet (404).
  Future<DocVersion?> document(String kind) async {
    try {
      return DocVersion.fromJson((await client.get('/documents/$kind')) as Json);
    } on ApiException catch (e) {
      if (e.status == 404) return null;
      rethrow;
    }
  }

  Future<String> acceptDocument(int documentId, {int? studentId}) async =>
      ((await client.post('/consents', {'document_id': documentId, 'student_id': studentId})) as Json)['version'] as String;
  Future<List<MyConsent>> myConsents() async => parseList(await client.get('/consents/my'), MyConsent.fromJson);
  Future<void> revokeConsent(int id) => client.post('/consents/$id/revoke');

  Future<List<Complaint>> myComplaints() async => parseList(await client.get('/complaints/my'), Complaint.fromJson);
  Future<Complaint> fileComplaint({required String subject, required String body, int? againstUserId}) async =>
      Complaint.fromJson((await client.post('/complaints',
          {'subject': subject, 'body': body, 'against_user_id': againstUserId})) as Json);
  Future<Complaint> appeal(int id) async =>
      Complaint.fromJson((await client.post('/complaints/$id', {'action': 'appeal'})) as Json);
}
