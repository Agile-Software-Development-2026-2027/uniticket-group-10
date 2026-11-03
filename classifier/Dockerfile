# Il classificatore come servizio per il widget: GET /health e POST /conversation sulla porta 8001.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /build
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN ./mvnw -q -B dependency:go-offline
COPY src src
RUN ./mvnw -q -B package -DskipTests

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /build/target/uniticket-chatbot.jar ./
COPY data/catalog.json data/structures-extra.json ./data/
# La cache degli embedding si scrive alla prima partenza con Ollama.
RUN mkdir -p data/cache && chown 10001:10001 data/cache
USER 10001:10001
EXPOSE 8001
CMD ["java", "-jar", "uniticket-chatbot.jar", "serve", "--port", "8001"]
