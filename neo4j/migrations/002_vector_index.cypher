// Vector index for CodeNode.embedding (OpenAI text-embedding-3-small default: 1536 dimensions)
// Run after 001_constraints.cypher. Requires Neo4j 5.x with vector index support.

CREATE VECTOR INDEX node_embedding_idx IF NOT EXISTS
FOR (n:CodeNode)
ON (n.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};
