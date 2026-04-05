package com.pranapulse.core.social.web;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record CreateSocialConnectionRequest(@NotNull UUID targetUserId) {
}
