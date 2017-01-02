#!/bin/bash
docker stop floatyboat
docker rm floatyboat
docker rmi floatyboat
docker build -t floatyboat .
docker run -d -p 1337:1337 --restart always --name floatyboat floatyboat