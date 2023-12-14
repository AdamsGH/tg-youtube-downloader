.PHONY: build run stop rm

build:
	docker-compose build

run:
	docker-compose up -d

stop:
	docker-compose down

rm:
	docker rmi youtube-downloader-telegram

rebuild: stop rm build run
