// ContentAlchemy - MongoDB initialization script
//
// Creates the collections, indexes and (lenient) JSON-schema validators that the
// repositories in src/repositories/ rely on, and seeds the default local user.
// The script is idempotent: run it as often as you like.
//
// Usage
//   Local:   mongosh "mongodb://127.0.0.1:27017" scripts/init_mongodb.js
//   Atlas:   mongosh "mongodb+srv://<cluster>/" --username <user> scripts/init_mongodb.js
//   Docker:  mounted into /docker-entrypoint-initdb.d/ by docker-compose.yml and run
//            automatically the first time the mongodb volume is created.
//
// Environment variables (all optional)
//   MONGODB_DATABASE         database name               (default: contentalchemy_db)
//   CONTENTALCHEMY_USER_ID   user the Streamlit app runs as (default: usr_local_001)
//   CONTENTALCHEMY_USERNAME  display name for that user   (default: Local User)

const env = (typeof process !== "undefined" && process.env) ? process.env : {};

const DB_NAME = env.MONGODB_DATABASE || "contentalchemy_db";
const USER_ID = env.CONTENTALCHEMY_USER_ID || "usr_local_001";
const USERNAME = env.CONTENTALCHEMY_USERNAME || "Local User";

const database = db.getSiblingDB(DB_NAME);

print(`ContentAlchemy: initializing database "${DB_NAME}"`);

// ---------------------------------------------------------------------------
// Enumerations, kept in sync with src/repositories/*.py
// ---------------------------------------------------------------------------

const CONTENT_TYPES = ["research", "seo_blog", "linkedin", "image", "strategy", "multi", "chat"];
const CONVERSATION_STATUSES = ["active", "awaiting_approval", "completed", "failed", "archived"];
const MESSAGE_ROLES = ["user", "assistant", "system", "tool"];

// ---------------------------------------------------------------------------
// Validators
//
// validationAction "warn" logs schema violations instead of rejecting writes, so
// the validators document the expected shape without ever breaking the app.
// Switch to "error" once you are confident every writer complies.
// ---------------------------------------------------------------------------

const validators = {
  users: {
    $jsonSchema: {
      bsonType: "object",
      required: ["user_id", "username", "auth_provider", "auth_subject", "created_at"],
      properties: {
        user_id: { bsonType: "string" },
        username: { bsonType: "string" },
        auth_provider: { bsonType: "string" },
        auth_subject: { bsonType: "string" },
        is_active: { bsonType: "bool" },
        created_at: { bsonType: "date" },
      },
    },
  },

  user_profiles: {
    $jsonSchema: {
      bsonType: "object",
      required: ["user_id", "conversation_id", "profile_markdown"],
      properties: {
        user_id: { bsonType: "string" },
        conversation_id: { bsonType: "string" },
        profile_markdown: { bsonType: "string" },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },

  conversations: {
    $jsonSchema: {
      bsonType: "object",
      required: ["conversation_id", "user_id", "thread_id", "content_type", "title", "status", "created_at", "updated_at"],
      properties: {
        conversation_id: { bsonType: "string", pattern: "^conv_" },
        user_id: { bsonType: "string" },
        thread_id: { bsonType: "string" },
        content_type: { enum: CONTENT_TYPES },
        title: { bsonType: "string" },
        topic: { bsonType: "string" },
        target_audience: { bsonType: "string" },
        tone: { bsonType: "string" },
        status: { enum: CONVERSATION_STATUSES },
        metadata: { bsonType: "object" },
        last_message_sequence: { bsonType: ["int", "long"] },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },

  messages: {
    $jsonSchema: {
      bsonType: "object",
      required: ["message_id", "conversation_id", "user_id", "sequence", "role", "message_type", "content_type", "content", "created_at"],
      properties: {
        message_id: { bsonType: "string", pattern: "^msg_" },
        conversation_id: { bsonType: "string" },
        user_id: { bsonType: "string" },
        sequence: { bsonType: ["int", "long"] },
        role: { enum: MESSAGE_ROLES },
        message_type: { bsonType: "string" },
        content_type: { enum: CONTENT_TYPES },
        agent_name: { bsonType: ["string", "null"] },
        metadata: { bsonType: "object" },
        status: { bsonType: "string" },
        created_at: { bsonType: "date" },
        updated_at: { bsonType: "date" },
      },
    },
  },
};

// ---------------------------------------------------------------------------
// Indexes
//
// Names match the ensure_indexes() functions in src/repositories/ so running the
// Python helpers afterwards is a no-op. The application never calls
// ensure_indexes() for conversations or messages itself, so run this script.
// ---------------------------------------------------------------------------

const indexes = {
  users: [
    // create_user() upserts on (auth_provider, auth_subject).
    { key: { auth_provider: 1, auth_subject: 1 }, options: { name: "uq_user_auth", unique: true } },
    // get_user_by_id() / update_username() look up by user_id.
    { key: { user_id: 1 }, options: { name: "uq_user_id", unique: true } },
  ],

  user_profiles: [
    // profile_repository.ensure_indexes(): one profile per user per conversation.
    { key: { user_id: 1, conversation_id: 1 }, options: { name: "uq_profile_user_conversation", unique: true } },
  ],

  conversations: [
    { key: { conversation_id: 1 }, options: { name: "uq_conversation_id", unique: true } },
    { key: { thread_id: 1 }, options: { name: "uq_conversation_thread_id", unique: true } },
    // list_conversations(): history sidebar, newest first.
    { key: { user_id: 1, updated_at: -1 }, options: { name: "ix_conversations_user_updated" } },
    // list_conversations(status="completed"): content dashboard.
    { key: { user_id: 1, status: 1, updated_at: -1 }, options: { name: "ix_conversations_user_status_updated" } },
  ],

  messages: [
    { key: { message_id: 1 }, options: { name: "uq_message_id", unique: true } },
    // add_message() allocates sequence numbers per conversation; list_messages() sorts by them.
    { key: { conversation_id: 1, sequence: 1 }, options: { name: "uq_message_conversation_sequence", unique: true } },
    // Time-ordered reads within a conversation (matches the index found in existing databases).
    { key: { conversation_id: 1, created_at: 1 }, options: { name: "ix_messages_conversation_created" } },
    // list_user_messages_by_type(): content dashboard (generated_content / final_content), newest first.
    // Added by this script; not created by message_repository.ensure_indexes().
    { key: { user_id: 1, message_type: 1, created_at: -1 }, options: { name: "ix_messages_user_type_created" } },
  ],
};

// Note: message_repository.ensure_indexes() declares "ix_messages_conversation_created" on
// (conversation_id, sequence), the same keys as uq_message_conversation_sequence, which MongoDB
// rejects. Existing databases have it on (conversation_id, created_at), which is what is used here.

// ---------------------------------------------------------------------------
// Apply
// ---------------------------------------------------------------------------

const existing = new Set(database.getCollectionNames());

for (const [name, validator] of Object.entries(validators)) {
  if (existing.has(name)) {
    database.runCommand({ collMod: name, validator, validationLevel: "moderate", validationAction: "warn" });
    print(`  collection ${name}: exists, validator updated`);
  } else {
    database.createCollection(name, { validator, validationLevel: "moderate", validationAction: "warn" });
    print(`  collection ${name}: created`);
  }
}

for (const [name, specs] of Object.entries(indexes)) {
  const collection = database.getCollection(name);
  const current = collection.getIndexes();

  for (const { key, options } of specs) {
    const sameKey = current.find((index) => JSON.stringify(index.key) === JSON.stringify(key));

    if (sameKey && sameKey.name !== options.name) {
      print(`  index ${name}.${options.name}: skipped, keys already covered by "${sameKey.name}"`);
      continue;
    }

    try {
      collection.createIndex(key, options);
      print(`  index ${name}.${options.name}: ok`);
    } catch (error) {
      // Usually duplicate data blocking a unique index. Report and continue.
      print(`  index ${name}.${options.name}: FAILED - ${error.message}`);
    }
  }
}

// ---------------------------------------------------------------------------
// Seed the local user (src/web_app/assistant.py: get_current_user)
// ---------------------------------------------------------------------------

database.users.updateOne(
  { auth_provider: "local", auth_subject: USER_ID },
  {
    $setOnInsert: {
      user_id: USER_ID,
      auth_provider: "local",
      auth_subject: USER_ID,
      created_at: new Date(),
      is_active: true,
    },
    $set: { username: USERNAME },
  },
  { upsert: true },
);

print(`  user ${USER_ID} ("${USERNAME}"): ready`);
print("ContentAlchemy: database initialization complete");
