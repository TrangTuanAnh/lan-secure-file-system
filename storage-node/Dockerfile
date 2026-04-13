# Multi-stage build for Storage Node
FROM maven:3.9-eclipse-temurin-17 AS builder

# Set working directory
WORKDIR /build

# Copy pom.xml first for dependency caching
COPY pom.xml .

# Download dependencies (cached layer)
RUN mvn dependency:go-offline -B

# Copy source code
COPY src ./src

# Build the application
RUN mvn clean package -DskipTests

# Runtime stage
FROM eclipse-temurin:17-jre-alpine

# Set working directory
WORKDIR /app

# Create directories for storage
RUN mkdir -p /app/data/store /app/data/temp /app/data/meta /app/logs

# Copy the built JAR from builder stage
COPY --from=builder /build/target/storage-node-*.jar /app/storage-node.jar

# Copy configuration file (use docker-specific config)
COPY storage-node.docker.properties /app/storage-node.properties

# Expose ports
# Data plane port (for client connections)
EXPOSE 9001

# Set environment variables
ENV JAVA_OPTS="-Xmx512m -Xms256m"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD nc -z localhost 9001 || exit 1

# Run the application
CMD ["sh", "-c", "java $JAVA_OPTS -jar storage-node.jar storage-node.properties"]
