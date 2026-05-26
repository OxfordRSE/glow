FROM ghcr.io/enketo/enketo:7.5.1

ENV ENKETO_SRC_DIR=/srv/src/enketo/packages/enketo-express
WORKDIR ${ENKETO_SRC_DIR}

COPY envsub.awk /scripts/envsub.awk
COPY config.json.template ${ENKETO_SRC_DIR}/config/config.json.template
COPY config.json.template ${ENKETO_SRC_DIR}/config/config.json
COPY start-enketo.sh ${ENKETO_SRC_DIR}/start-enketo.sh

RUN chmod +x /scripts/envsub.awk ${ENKETO_SRC_DIR}/start-enketo.sh

EXPOSE 8005

CMD ["./start-enketo.sh"]
