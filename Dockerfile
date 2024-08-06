# FROM jekyll/jekyll
# Label MAINTAINER Amir Pourmand


# #install imagemagick tool for convert command
# RUN apk add --no-cache --virtual .build-deps \
#         libxml2-dev \
#         shadow \
#         autoconf \
#         g++ \
#         make \
#     && apk add --no-cache imagemagick-dev imagemagick \
#     && apk add jekyll-redirect-from


# WORKDIR /srv/jekyll
# ADD Gemfile /srv/jekyll/


# RUN bundle install

FROM amirpourmand/al-folio

# Set working directory
WORKDIR /srv/jekyll

ADD Gemfile /srv/jekyll/
# Copy the Gemfile and Gemfile.lock
# COPY Gemfile Gemfile.lock ./

# Install bundler and gems
RUN gem install bundler && bundle install

# Copy the rest of the site
COPY . .

# Expose the port Jekyll uses
EXPOSE 8080

# Command to build and serve the site
CMD ["jekyll", "serve", "--watch", "--port=8080", "--host=0.0.0.0", "--livereload", "--verbose"]

