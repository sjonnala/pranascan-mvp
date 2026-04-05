CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE core.users (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    oidc_subject VARCHAR(128) NOT NULL,
    email VARCHAR(320),
    display_name VARCHAR(120) NOT NULL,
    phone_e164 VARCHAR(20),
    avatar_url VARCHAR(512),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    CONSTRAINT uk_users_oidc_subject UNIQUE (oidc_subject),
    CONSTRAINT uk_users_email UNIQUE (email),
    CONSTRAINT uk_users_phone_e164 UNIQUE (phone_e164)
);

CREATE TABLE core.vitality_streaks (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    user_id UUID NOT NULL,
    current_streak_days INTEGER NOT NULL DEFAULT 0,
    longest_streak_days INTEGER NOT NULL DEFAULT 0,
    last_check_in_on DATE,
    streak_started_on DATE,
    grace_window_ends_on DATE,
    status VARCHAR(32) NOT NULL,
    CONSTRAINT fk_vitality_streaks_user
        FOREIGN KEY (user_id) REFERENCES core.users (id),
    CONSTRAINT uk_vitality_streaks_user_id UNIQUE (user_id)
);

CREATE INDEX idx_vitality_streaks_status ON core.vitality_streaks (status);

CREATE TABLE core.social_connections (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    requester_user_id UUID NOT NULL,
    addressee_user_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    responded_at TIMESTAMPTZ,
    CONSTRAINT fk_social_connections_requester
        FOREIGN KEY (requester_user_id) REFERENCES core.users (id),
    CONSTRAINT fk_social_connections_addressee
        FOREIGN KEY (addressee_user_id) REFERENCES core.users (id),
    CONSTRAINT uk_social_connections_pair
        UNIQUE (requester_user_id, addressee_user_id),
    CONSTRAINT chk_social_connections_not_self
        CHECK (requester_user_id <> addressee_user_id)
);

CREATE INDEX idx_social_connections_requester_user_id ON core.social_connections (requester_user_id);
CREATE INDEX idx_social_connections_addressee_user_id ON core.social_connections (addressee_user_id);
CREATE INDEX idx_social_connections_status ON core.social_connections (status);
