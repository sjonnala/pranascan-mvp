package com.pranapulse.core.audit.web;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class AuditControllerIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void listsCoreOwnedAuditLogsAfterAuthenticatedRequest() throws Exception {
        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(jwt -> jwt
                                .subject("oidc-audit-user-1")
                                .claim("email", "audit-user-1@example.com")
                                .claim("name", "Audit User 1"))))
                .andExpect(status().isOk());

        MvcResult auditLogs = mockMvc.perform(get("/api/v1/audit/logs")
                        .with(jwt().jwt(jwt -> jwt
                                .subject("oidc-audit-user-1")
                                .claim("email", "audit-user-1@example.com")
                                .claim("name", "Audit User 1"))))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode payload = objectMapper.readTree(auditLogs.getResponse().getContentAsString());
        assertTrue(payload.get("total").asInt() >= 1);
        assertTrue(payload.get("items").toString().contains("GET:/api/v1/auth/me"));
    }
}
