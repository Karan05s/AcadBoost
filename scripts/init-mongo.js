// MongoDB initialization script
// This script runs when the MongoDB container starts for the first time

// Switch to the learning_analytics database
db = db.getSiblingDB("learning_analytics");

// Create collections with validation schemas
db.createCollection("user_profiles", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["user_id", "email", "role"],
      properties: {
        user_id: { bsonType: "string" },
        email: { bsonType: "string" },
        role: {
          bsonType: "string",
          enum: ["student", "instructor", "admin"],
        },
        created_at: { bsonType: "date" },
      },
    },
  },
});

db.createCollection("student_performance", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["student_id", "submission_type", "timestamp"],
      properties: {
        student_id: { bsonType: "string" },
        submission_type: {
          bsonType: "string",
          enum: ["quiz", "code"],
        },
        timestamp: { bsonType: "date" },
        score: { bsonType: "number" },
      },
    },
  },
});

db.createCollection("learning_gaps");
db.createCollection("recommendations");

print("MongoDB initialization completed successfully");
