docker run -p 8000:8000 -it \
    -v ${PWD}/.env.docker:/app/.env \
    -v ${PWD}/static:/app/static \
    -v ${PWD}/app:/app/app \
    -v ${PWD}/server_dev.py:/app/server_dev.py \
    -v ${PWD}/parser:/app/parser \
    general-chatbot-api-environment:0.0.1

# docker run -p 8000:8000 -it -v ${PWD}/.env.docker:/app/.env -v ${PWD}/static:/app/static -v ${PWD}/app:/app/app -v ${PWD}/server_dev.py:/app/server_dev.py -v ${PWD}/parser:/app/parser general-chatbot-api-environment:0.0.1