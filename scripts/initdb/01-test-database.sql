-- Separate database for backend integration tests so pytest never touches dev data.
CREATE DATABASE aperture_test OWNER aperture;
