#!/bin/bash

set -e


# Create an admin user
superset fab create-admin \
  --username admin \
  --firstname admin \
  --lastname admin \
  --email admin@example.com \
  --password admin 

# Initialize the database
superset db upgrade

# Create default roles and permissions
superset init
