// Data shapes of the One English API v1 (portal, chats, store, compliance). Unknown fields are ignored.

typedef Json = Map<String, dynamic>;

DateTime? _dt(Object? v) => v is String ? DateTime.tryParse(v) : null;
int _i(Object? v, [int d = 0]) => v is int ? v : (v is num ? v.toInt() : d);
int? _in(Object? v) => v is num ? v.toInt() : null;
String? _s(Object? v) => v is String ? v : null;
List<Json> _list(Object? v) => v is List ? v.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList() : const [];

class AuthMe {
  AuthMe({required this.id, required this.kind, required this.fullName, required this.phone, required this.locale,
      this.avatarUrl, this.rulesAcceptedVersion});
  factory AuthMe.fromJson(Json j) => AuthMe(
        id: _i(j['id']),
        kind: _s(j['kind']) ?? '',
        fullName: _s(j['full_name']) ?? '',
        phone: _s(j['phone']) ?? '',
        locale: _s(j['locale']) ?? 'ru',
        avatarUrl: _s(j['avatar_url']),
        rulesAcceptedVersion: _s(j['rules_accepted_version']),
      );
  final int id;
  final String kind;
  final String fullName;
  final String phone;
  final String locale;
  final String? avatarUrl;
  String? rulesAcceptedVersion;

  bool get isParent => kind == 'parent';
  bool get isStudent => kind == 'student';
  bool get isPortal => isParent || isStudent;
}

class Branch {
  Branch({required this.id, required this.name, this.phone, this.address});
  factory Branch.fromJson(Json j) =>
      Branch(id: _i(j['id']), name: _s(j['name']) ?? '', phone: _s(j['phone']), address: _s(j['address']));
  final int id;
  final String name;
  final String? phone;
  final String? address;
}

class GroupRef {
  GroupRef({required this.id, required this.name, this.level, this.teacher, this.teacherId, this.chatId});
  factory GroupRef.fromJson(Json j) => GroupRef(
      id: _i(j['id']),
      name: _s(j['name']) ?? '',
      level: _s(j['level']),
      teacher: _s(j['teacher']),
      teacherId: _in(j['teacher_id']),
      chatId: _in(j['chat_id']));
  final int id;
  final String name;
  final String? level;
  final String? teacher;
  final int? teacherId;
  final int? chatId;
}

class Child {
  Child({required this.id, required this.fullName, required this.branch, required this.groups, this.photoUrl,
      this.status = 'active', this.level, this.lessonsLeft = 0, this.moneyBalance = 0, this.debt = false,
      this.blocked = false, this.stars = 0, this.coins = 0});
  factory Child.fromJson(Json j) => Child(
        id: _i(j['id']),
        fullName: _s(j['full_name']) ?? '',
        photoUrl: _s(j['photo_url']),
        status: _s(j['status']) ?? 'active',
        branch: Branch.fromJson((j['branch'] as Map?)?.cast<String, dynamic>() ?? const {}),
        level: _s(j['level']),
        lessonsLeft: _i(j['lessons_left']),
        moneyBalance: _i(j['money_balance']),
        debt: j['debt'] == true,
        blocked: j['blocked'] == true,
        stars: _i(j['stars']),
        coins: _i(j['coins']),
        groups: _list(j['groups']).map(GroupRef.fromJson).toList(),
      );
  final int id;
  final String fullName;
  final String? photoUrl;
  final String status;
  final Branch branch;
  final String? level;
  final int lessonsLeft;
  final int moneyBalance;
  final bool debt;
  final bool blocked;
  final int stars;
  int coins;
  final List<GroupRef> groups;

  String get firstName => fullName.split(' ').first;
  GroupRef? get mainGroup => groups.isEmpty ? null : groups.first;
}

class PortalMe {
  PortalMe({required this.kind, required this.fullName, required this.children});
  factory PortalMe.fromJson(Json j) => PortalMe(
      kind: _s(j['kind']) ?? '',
      fullName: _s(j['full_name']) ?? '',
      children: _list(j['children']).map(Child.fromJson).toList());
  final String kind;
  final String fullName;
  final List<Child> children;
}

class Lesson {
  Lesson({required this.id, required this.startsAt, required this.endsAt, required this.status, this.group, this.room,
      this.teacher, this.cancelReason, this.topic});
  factory Lesson.fromJson(Json j) => Lesson(
        id: _i(j['id']),
        startsAt: _dt(j['starts_at']) ?? DateTime.now(),
        endsAt: _dt(j['ends_at']) ?? DateTime.now(),
        status: _s(j['status']) ?? 'planned',
        group: _s(j['group']),
        room: _s(j['room']),
        teacher: _s(j['teacher']),
        cancelReason: _s(j['cancel_reason']),
        topic: _s(j['topic']),
      );
  final int id;
  final DateTime startsAt;
  final DateTime endsAt;
  final String status;
  final String? group;
  final String? room;
  final String? teacher;
  final String? cancelReason;
  final String? topic;

  bool get cancelled => status == 'cancelled';
}

class Mark {
  Mark({required this.lessonId, required this.at, required this.status, this.group, this.grade, this.comment,
      this.stars, this.charged = false, this.myRating});
  factory Mark.fromJson(Json j) => Mark(
        lessonId: _i(j['lesson_id']),
        at: _dt(j['at']) ?? DateTime.now(),
        group: _s(j['group']),
        status: _s(j['status']) ?? 'present',
        grade: _in(j['grade']),
        comment: _s(j['comment']),
        stars: _in(j['stars']),
        charged: j['charged'] == true,
        myRating: _in(j['my_rating']),
      );
  final int lessonId;
  final DateTime at;
  final String? group;
  final String status;
  final int? grade;
  final String? comment;
  final int? stars;
  final bool charged;
  int? myRating;

  bool get attended => status == 'present' || status == 'late';

  /// The server accepts a rating for an attended lesson within 7 days.
  bool canRate(DateTime now) => attended && now.difference(at).inDays < 7;
}

class Attendance {
  Attendance({required this.items, required this.monthLessons, required this.monthPresent, this.monthRate});
  factory Attendance.fromJson(Json j) {
    final m = (j['month'] as Map?)?.cast<String, dynamic>() ?? const {};
    return Attendance(
      items: _list(j['items']).map(Mark.fromJson).toList(),
      monthLessons: _i(m['lessons']),
      monthPresent: _i(m['present']),
      monthRate: _in(m['rate']),
    );
  }
  final List<Mark> items;
  final int monthLessons;
  final int monthPresent;
  final int? monthRate;
}

class Homework {
  Homework({required this.id, required this.title, required this.status, this.body, this.dueAt, this.grade,
      this.teacherComment, this.answer, this.fileUrl});
  factory Homework.fromJson(Json j) => Homework(
        id: _i(j['id']),
        title: _s(j['title']) ?? '',
        body: _s(j['body']),
        dueAt: _dt(j['due_at']),
        status: _s(j['status']) ?? 'assigned',
        grade: _in(j['grade']),
        teacherComment: _s(j['teacher_comment']),
        answer: _s(j['answer']),
        fileUrl: _s(j['file_url']),
      );
  final int id;
  final String title;
  final String? body;
  final DateTime? dueAt;
  String status;
  final int? grade;
  final String? teacherComment;
  String? answer;
  String? fileUrl;

  bool overdue(DateTime now) => status == 'assigned' && dueAt != null && dueAt!.isBefore(now);
}

class PaymentItem {
  PaymentItem({required this.id, required this.paidAt, required this.category, required this.amount,
      required this.lessons, required this.method, this.refunded = 0, this.note});
  factory PaymentItem.fromJson(Json j) => PaymentItem(
        id: _i(j['id']),
        paidAt: _dt(j['paid_at']) ?? DateTime.now(),
        category: _s(j['category']) ?? 'course',
        amount: _i(j['amount']),
        lessons: _i(j['lessons']),
        method: _s(j['method']) ?? '',
        refunded: _i(j['refunded']),
        note: _s(j['note']),
      );
  final int id;
  final DateTime paidAt;
  final String category;
  final int amount;
  final int lessons;
  final String method;
  final int refunded;
  final String? note;
}

class Payments {
  Payments({required this.lessonsLeft, required this.moneyBalance, required this.debtLessons, required this.blocked,
      required this.items, this.lessonPrice});
  factory Payments.fromJson(Json j) => Payments(
        lessonsLeft: _i(j['lessons_left']),
        moneyBalance: _i(j['money_balance']),
        debtLessons: _i(j['debt_lessons']),
        lessonPrice: _in(j['lesson_price']),
        blocked: j['blocked'] == true,
        items: _list(j['items']).map(PaymentItem.fromJson).toList(),
      );
  final int lessonsLeft;
  final int moneyBalance;
  final int debtLessons;
  final int? lessonPrice;
  final bool blocked;
  final List<PaymentItem> items;

  int? get debtAmount => lessonPrice == null || debtLessons == 0 ? null : lessonPrice! * debtLessons;
  List<PaymentItem> get books => items.where((p) => p.category == 'book').toList();
}

class TestResult {
  TestResult({required this.id, required this.title, required this.kind, required this.score, required this.maxScore,
      this.finishedAt});
  factory TestResult.fromJson(Json j) => TestResult(
        id: _i(j['id']),
        title: _s(j['title']) ?? '',
        kind: _s(j['kind']) ?? '',
        score: _i(j['score']),
        maxScore: _i(j['max_score']),
        finishedAt: _dt(j['finished_at']),
      );
  final int id;
  final String title;
  final String kind;
  final int score;
  final int maxScore;
  final DateTime? finishedAt;
}

class ChatUser {
  ChatUser({required this.id, required this.fullName, required this.kind, this.position, this.subtitle});
  factory ChatUser.fromJson(Json j) => ChatUser(
      id: _i(j['id']),
      fullName: _s(j['full_name']) ?? '',
      kind: _s(j['kind']) ?? '',
      position: _s(j['position']),
      subtitle: _s(j['subtitle']));
  final int id;
  final String fullName;
  final String kind;
  final String? position;
  final String? subtitle;
}

class Chat {
  Chat({required this.id, required this.kind, required this.title, required this.unread, this.groupId,
      this.lastText, this.lastAt, this.lastSender, this.other, this.members = 0, this.aboutStudentId});
  factory Chat.fromJson(Json j) {
    final lm = (j['last_message'] as Map?)?.cast<String, dynamic>();
    final ou = (j['other_user'] as Map?)?.cast<String, dynamic>();
    return Chat(
      id: _i(j['id']),
      kind: _s(j['kind']) ?? 'direct',
      title: _s(j['title']) ?? '',
      groupId: _in(j['group_id']),
      unread: _i(j['unread']),
      lastText: _s(lm?['text']),
      lastAt: _dt(lm?['at']),
      lastSender: _s(lm?['sender']),
      other: ou == null ? null : ChatUser.fromJson(ou),
      members: _i(j['members']),
      aboutStudentId: _in(j['about_student_id']),
    );
  }
  final int id;
  final String kind;
  final String title;
  final int? groupId;
  int unread;
  String? lastText;
  DateTime? lastAt;
  String? lastSender;
  final ChatUser? other;
  final int members;

  /// The child the chat is about (parents; filled by the server where it can tell).
  final int? aboutStudentId;

  bool get isGroup => kind == 'group';
}

class ChatMessage {
  ChatMessage({required this.id, required this.chatId, required this.senderId, required this.at, required this.kind,
      this.senderName, this.senderKind, this.senderPosition, this.text, this.fileUrl, this.fileName, this.pinned = false,
      this.edited = false, this.hidden = false});
  factory ChatMessage.fromJson(Json j) => ChatMessage(
        id: _i(j['id']),
        chatId: _i(j['chat_id']),
        senderId: _i(j['sender_id']),
        senderName: _s(j['sender_name']),
        senderKind: _s(j['sender_kind']),
        senderPosition: _s(j['sender_position']),
        at: _dt(j['at']) ?? DateTime.now(),
        kind: _s(j['kind']) ?? 'text',
        text: _s(j['text']),
        fileUrl: _s(j['file_url']),
        fileName: _s(j['file_name']),
        pinned: j['pinned'] == true,
        edited: j['edited'] == true,
        hidden: j['hidden'] == true,
      );
  final int id;
  final int chatId;
  final int senderId;
  final String? senderName;
  final String? senderKind;

  /// Staff job title («Преподаватель», «Менеджер»…); null for students and parents.
  final String? senderPosition;
  final DateTime at;
  final String kind;
  String? text;
  String? fileUrl;
  final String? fileName;
  bool pinned;
  final bool edited;
  bool hidden;
}

class UploadedFile {
  UploadedFile({required this.key, required this.url, required this.name, required this.size});
  factory UploadedFile.fromJson(Json j) =>
      UploadedFile(key: _s(j['key']) ?? '', url: _s(j['url']) ?? '', name: _s(j['name']) ?? '', size: _i(j['size']));
  final String key;
  final String url;
  final String name;
  final int size;
}

class Notice {
  Notice({required this.id, required this.at, required this.kind, required this.title, this.body, this.link,
      this.read = false});
  factory Notice.fromJson(Json j) => Notice(
        id: _i(j['id']),
        at: _dt(j['at']) ?? DateTime.now(),
        kind: _s(j['kind']) ?? '',
        title: _s(j['title']) ?? '',
        body: _s(j['body']),
        link: _s(j['link']),
        read: j['read'] == true,
      );
  final int id;
  final DateTime at;
  final String kind;
  final String title;
  final String? body;
  final String? link;
  bool read;
}

class CoinEntry {
  CoinEntry({required this.at, required this.kind, required this.delta, this.reason});
  factory CoinEntry.fromJson(Json j) =>
      CoinEntry(at: _dt(j['at']) ?? DateTime.now(), kind: _s(j['kind']) ?? '', delta: _i(j['delta']), reason: _s(j['reason']));
  final DateTime at;
  final String kind;
  final int delta;
  final String? reason;
}

class CoinHistory {
  CoinHistory({required this.balance, required this.items});
  factory CoinHistory.fromJson(Json j) =>
      CoinHistory(balance: _i(j['balance']), items: _list(j['items']).map(CoinEntry.fromJson).toList());
  final int balance;
  final List<CoinEntry> items;

  /// Coins earned over the last 7 days (shop holds and refunds excluded).
  int earnedSince(DateTime since) => items
      .where((e) => e.at.isAfter(since) && e.delta > 0 && !e.kind.startsWith('order_'))
      .fold(0, (a, e) => a + e.delta);
}

class ShopItem {
  ShopItem({required this.id, required this.name, required this.priceCoins, required this.stock, this.icon,
      this.photoUrl});
  factory ShopItem.fromJson(Json j) => ShopItem(
        id: _i(j['id']),
        name: _s(j['name']) ?? '',
        priceCoins: _i(j['price_coins']),
        stock: _i(j['stock']),
        icon: _s(j['icon']),
        photoUrl: _s(j['photo_url']),
      );
  final int id;
  final String name;
  final int priceCoins;
  int stock;
  final String? icon;
  final String? photoUrl;
}

class ShopOrder {
  ShopOrder({required this.id, required this.item, required this.coins, required this.status, this.createdAt,
      this.issuedAt});
  factory ShopOrder.fromJson(Json j) => ShopOrder(
        id: _i(j['id']),
        item: _s(j['item']) ?? '',
        coins: _i(j['coins']),
        status: _s(j['status']) ?? 'placed',
        createdAt: _dt(j['created_at']),
        issuedAt: _dt(j['issued_at']),
      );
  final int id;
  final String item;
  final int coins;
  String status;
  final DateTime? createdAt;
  final DateTime? issuedAt;

  bool get open => status == 'placed' || status == 'ready';
}

class LeaderRow {
  LeaderRow({required this.name, required this.coins});
  factory LeaderRow.fromJson(Json j) => LeaderRow(name: _s(j['name']) ?? '', coins: _i(j['coins']));
  final String name;
  final int coins;
}

class Complaint {
  Complaint({required this.id, required this.subject, required this.body, required this.status, this.createdAt,
      this.dueAt, this.answer, this.answeredAt});
  factory Complaint.fromJson(Json j) => Complaint(
        id: _i(j['id']),
        subject: _s(j['subject']) ?? '',
        body: _s(j['body']) ?? '',
        status: _s(j['status']) ?? 'new',
        createdAt: _dt(j['created_at']),
        dueAt: _dt(j['due_at']),
        answer: _s(j['answer']),
        answeredAt: _dt(j['answered_at']),
      );
  final int id;
  final String subject;
  final String body;
  final String status;
  final DateTime? createdAt;
  final DateTime? dueAt;
  final String? answer;
  final DateTime? answeredAt;
}

class DocVersion {
  DocVersion({required this.id, required this.kind, required this.version, required this.title, required this.body,
      this.effectiveFrom, this.upcomingVersion, this.upcomingFrom});
  factory DocVersion.fromJson(Json j) {
    final up = (j['upcoming'] as Map?)?.cast<String, dynamic>();
    return DocVersion(
      id: _i(j['id']),
      kind: _s(j['kind']) ?? '',
      version: _s(j['version']) ?? '',
      title: _s(j['title']) ?? '',
      body: _s(j['body']) ?? '',
      effectiveFrom: _dt(j['effective_from']),
      upcomingVersion: _s(up?['version']),
      upcomingFrom: _dt(up?['effective_from']),
    );
  }
  final int id;
  final String kind;
  final String version;
  final String title;
  final String body;
  final DateTime? effectiveFrom;
  final String? upcomingVersion;
  final DateTime? upcomingFrom;
}

class MyConsent {
  MyConsent({required this.id, required this.documentId, required this.kind, required this.version, this.studentId,
      this.acceptedAt, this.revokedAt});
  factory MyConsent.fromJson(Json j) => MyConsent(
        id: _i(j['id']),
        documentId: _i(j['document_id']),
        kind: _s(j['kind']) ?? '',
        version: _s(j['version']) ?? '',
        studentId: _in(j['student_id']),
        acceptedAt: _dt(j['accepted_at']),
        revokedAt: _dt(j['revoked_at']),
      );
  final int id;
  final int documentId;
  final String kind;
  final String version;
  final int? studentId;
  final DateTime? acceptedAt;
  final DateTime? revokedAt;
}

class SessionInfo {
  SessionInfo({required this.id, required this.current, this.userAgent, this.ip, this.lastUsedAt, this.createdAt});
  factory SessionInfo.fromJson(Json j) => SessionInfo(
        id: _i(j['id']),
        current: j['current'] == true,
        userAgent: _s(j['user_agent']),
        ip: _s(j['ip']),
        lastUsedAt: _dt(j['last_used_at']),
        createdAt: _dt(j['created_at']),
      );
  final int id;
  final bool current;
  final String? userAgent;
  final String? ip;
  final DateTime? lastUsedAt;
  final DateTime? createdAt;
}

List<T> parseList<T>(Object? data, T Function(Json) f) => _list(data).map(f).toList();

int _money(Object? v) => v is num ? v.round() : (v is String ? (double.tryParse(v)?.round() ?? 0) : 0);

class OwnedBook {
  OwnedBook({required this.bookId, required this.title, required this.qty, required this.price, this.at});
  factory OwnedBook.fromJson(Json j) =>
      OwnedBook(bookId: _i(j['book_id']), title: _s(j['title']) ?? '', qty: _i(j['qty'], 1), price: _money(j['price']), at: _dt(j['at']));
  final int bookId;
  final String title;
  final int qty;
  final int price;
  final DateTime? at;
}

class NeededBook {
  NeededBook({required this.id, required this.title, required this.price});
  factory NeededBook.fromJson(Json j) => NeededBook(id: _i(j['id']), title: _s(j['title']) ?? '', price: _money(j['price']));
  final int id;
  final String title;
  final int price;
}

/// GET /students/{id}/books: what the student got, and what their level still needs.
class StudentBooks {
  StudentBooks({required this.items, required this.needed});
  factory StudentBooks.fromJson(Json j) => StudentBooks(
      items: _list(j['items']).map(OwnedBook.fromJson).toList(), needed: _list(j['needed']).map(NeededBook.fromJson).toList());
  final List<OwnedBook> items;
  final List<NeededBook> needed;
}
