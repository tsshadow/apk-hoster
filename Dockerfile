# Build stage
FROM golang:alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o apk-hoster main.go

# Final stage
FROM alpine:latest

WORKDIR /app
COPY --from=builder /app/apk-hoster .
# Create dist directory, will be populated via volume mount
RUN mkdir -p dist

EXPOSE 8275
CMD ["./apk-hoster"]
