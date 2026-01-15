FROM continuumio/miniconda3

COPY src/notulen/azure_infra/post_transcribe_job/conda-post-transcribe.yaml .
RUN conda env create -f conda-post-transcribe.yaml -n alliantieai

# make sure future RUN commands run inside the created conda environment
SHELL ["conda", "run", "-n", "alliantieai", "/bin/bash", "-c"]


ARG BUILD_TAG=1
ENV BUILD_TAG=$BUILD_TAG

# Start and enable SSH
COPY entrypoint.sh ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends dialog \
    && apt-get install -y --no-install-recommends openssh-server \
    && echo "root:Docker!" | chpasswd \
    && chmod u+x ./entrypoint.sh

# COPY src/webapp /opt/webapp
COPY src src
COPY webapp_src webapp_src

COPY setup.py setup.py
RUN pip install -e .


COPY sshd_config /etc/ssh/

# Copy streamlit config
COPY .streamlit .streamlit

EXPOSE 8080 2222

HEALTHCHECK CMD curl --fail http://localhost:8080/_stcore/health

ENTRYPOINT ["./entrypoint.sh" ]