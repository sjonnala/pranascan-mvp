package com.pranapulse.core.audit.web;

import com.pranapulse.core.audit.application.AuditLogService;
import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/audit")
public class AuditController {

    private final AuthenticatedUserService authenticatedUserService;
    private final AuditLogService auditLogService;

    public AuditController(
            AuthenticatedUserService authenticatedUserService,
            AuditLogService auditLogService
    ) {
        this.authenticatedUserService = authenticatedUserService;
        this.auditLogService = auditLogService;
    }

    @GetMapping("/logs")
    public AuditLogListResponse listLogs(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(name = "user_id", required = false) UUID requestedUserId,
            @RequestParam(name = "action", required = false) String action,
            @RequestParam(name = "page", defaultValue = "1") int page,
            @RequestParam(name = "page_size", defaultValue = "50") int pageSize
    ) {
        User user = authenticatedUserService.getOrProvisionUser(jwt);
        if (requestedUserId != null && !requestedUserId.equals(user.getId())) {
            throw new AccessDeniedException("You do not have access to this audit log slice.");
        }
        return AuditLogListResponse.from(auditLogService.list(user.getId(), action, page, pageSize));
    }
}
